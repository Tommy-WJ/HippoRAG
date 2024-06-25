import json
import re
from typing import List

import numpy as np
import torch


def get_file_name(path):
    return path.split('/')[-1].replace('.jsonl', '').replace('.json', '')


def mean_pooling(token_embeddings, mask):
    token_embeddings = token_embeddings.masked_fill(~mask[..., None].bool(), 0.)
    sentence_embeddings = token_embeddings.sum(dim=1) / mask.sum(dim=1)[..., None]
    return sentence_embeddings


def mean_pooling_embedding(input_str: str, tokenizer, model, device='cuda'):
    inputs = tokenizer(input_str, padding=True, truncation=True, return_tensors='pt').to(device)
    outputs = model(**inputs)

    embedding = mean_pooling(outputs[0], inputs['attention_mask']).to('cpu').detach().numpy()
    return embedding


def mean_pooling_embedding_with_normalization(input_str, tokenizer, model, device='cuda'):
    encoding = tokenizer(input_str, return_tensors='pt', padding=True, truncation=True)
    input_ids = encoding['input_ids']
    attention_mask = encoding['attention_mask']
    input_ids = input_ids.to(device)
    attention_mask = attention_mask.to(device)
    outputs = model(input_ids, attention_mask=attention_mask)
    embeddings = mean_pooling(outputs[0], attention_mask)
    embeddings = embeddings.T.divide(torch.linalg.norm(embeddings, dim=1)).T

    return embeddings


def processing_phrases(phrase):
    return re.sub('[^A-Za-z0-9 ]', ' ', phrase.lower()).strip()


def extract_json_dict(text):
    pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\})*)*\})*)*\}'
    match = re.search(pattern, text)

    if match:
        json_string = match.group()
        try:
            json_dict = json.loads(json_string)
            return json_dict
        except json.JSONDecodeError:
            return ''
    else:
        return ''


def min_max_normalize(x):
    return (x - np.min(x)) / (np.max(x) - np.min(x))


def softmax_with_zeros(logits):
    mask = (logits != 0)

    exp_logits = np.exp(logits[mask] - np.max(logits[mask]))
    probabilities = np.zeros_like(logits)
    probabilities[mask] = exp_logits / np.sum(exp_logits)

    return probabilities


def deduplicate_triples(triples: list):
    unique_triples = set()
    deduplicated_triples = []
    for triple in triples:
        if tuple(triple) not in unique_triples:
            unique_triples.add(tuple(triple))
            deduplicated_triples.append(triple)

    return deduplicated_triples


def fix_broken_generated_json(json_str: str):
    last_comma_index = json_str.rfind(',')
    if last_comma_index != -1:
        json_str = json_str[:last_comma_index]

    processed_string = json_str + ']\n}'
    return processed_string
