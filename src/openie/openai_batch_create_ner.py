import sys

sys.path.append('.')

import argparse
import json

from src.langchain_util import num_tokens_by_tiktoken
from src.openie_extraction_instructions import ner_output_one_shot, ner_input_one_shot, ner_instruction
from src.openie_with_retrieval_option_parallel import load_corpus


def named_entity_recognition_for_corpus_openai_batch(dataset_name: str, num_passages, model_name: str, max_tokens=4096):
    arg_str, dataset_name, flags_present, num_passages, retrieval_corpus = load_corpus(dataset_name, model_name,
                                                                                       num_passages, True)

    # output corpus to a file to upload to OpenAI
    corpus_jsonl_path = f'output/openai_batch_submission_ner_{dataset_name[1:]}_{model_name}.jsonl'
    jsonl_contents = []
    total_tokens = 0
    for idx, passage in enumerate(retrieval_corpus):
        ner_messages = [{'role': 'system', 'content': ner_instruction},
                        {'role': 'user', 'content': ner_input_one_shot},
                        {'role': 'assistant', 'content': ner_output_one_shot},
                        {'role': 'user', 'content': f"Paragraph:```\n{passage['passage']}\n```"}]
        total_tokens += num_tokens_by_tiktoken(str(ner_messages))
        idx = passage['idx'] if 'idx' in passage else idx

        # custom_id must be string
        jsonl_contents.append(json.dumps(
            {"custom_id": str(idx), "method": "POST", "url": "/v1/chat/completions",
             "body": {"model": model_name, "messages": ner_messages,
                      "max_tokens": max_tokens, "response_format": {"type": "json_object"}}}))

    print("Total prompt tokens:", total_tokens)
    print("Approximate costs for prompt tokens using GPT-4o-mini Batch API:", round(0.075 * total_tokens / 1e6, 3))
    print("Approximate costs for prompt tokens using GPT-3.5-turbo-0125 Batch API", round(0.25 * total_tokens / 1e6, 3))
    print("Approximate costs for prompt tokens using GPT-4o Batch API:", round(2.5 * total_tokens / 1e6, 3))

    # Save to the batch file
    with open(corpus_jsonl_path, 'w') as f:
        f.write('\n'.join(jsonl_contents))
    print("Batch file saved to", corpus_jsonl_path, 'len: ', len(jsonl_contents))

    # Call OpenAI Batch API
    from openai import OpenAI
    client = OpenAI(max_retries=5, timeout=60)
    batch_input_file = client.files.create(file=open(corpus_jsonl_path, 'rb'), purpose='batch')
    batch_obj = client.batches.create(input_file_id=batch_input_file.id, endpoint='/v1/chat/completions',
                                      completion_window='24h',
                                      metadata={'description': f"HippoRAG OpenIE for {dataset_name}, len: {len(jsonl_contents)}"})
    print(batch_obj)
    print()
    print("Go to https://platform.openai.com/batches/ or use OpenAI file API to get the output file ID after the batch job is done.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=str)
    parser.add_argument('--num_passages', type=str, default='all')
    parser.add_argument('--model_name', type=str, default='gpt-4o-mini', help='Specific model name')
    args = parser.parse_args()

    named_entity_recognition_for_corpus_openai_batch(args.dataset, args.num_passages, args.model_name)
