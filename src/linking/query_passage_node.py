import difflib
import json
from typing import Union

import numpy as np
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

from src.hipporag import get_query_instruction, HippoRAG
from src.linking import graph_search_with_entities

system_prompt = """Given a question, potential supporting passages, and a list of phrases (entities or literals) extracted from each passage, select the phrases that are most relevant to the question.
- Only select the given phrases that are relevant to the question and do not generate new ones.
- Relevance means the phrase is directly mentioned in the question or is essential for reasoning.
- Select all relevant ones but the number of selected phrases should be less than or equal to 5.
- Select the exact original phrases in the candidate list, NOT any stemmed or normalized forms.
- Respond in JSON format."""

demo_input = """Question: What is the capital of France?

Passage 1: Paris is the capital of an France, where it is located in Europe.
Phrases: ["paris", "france", "europe"]

Passage 2: Berlin is the capital of Germany.
Phrases: ["berlin", "germany"]"""

demo_output = """{"phrases": ["paris", "france"]}"""


def generate_nodes(hipporag: HippoRAG, query: str, docs: list, phrases_by_doc: list):
    user_prompt = f"Question: {query}"
    for i, doc in enumerate(docs):
        user_prompt += f"\n\nPassage {i + 1}: {doc}\nPhrases: {phrases_by_doc[i]}"

    messages = [
        SystemMessage(system_prompt),
        HumanMessage(demo_input),
        AIMessage(demo_output),
        HumanMessage(user_prompt),
    ]
    messages = ChatPromptTemplate.from_messages(messages).format_prompt()
    completion = hipporag.client.invoke(messages.to_messages(), temperature=0, response_format={"type": "json_object"})
    contents = completion.content
    selected_nodes = set()

    try:
        selected_nodes = set(json.loads(contents)["phrases"])
    except Exception as e:
        hipporag.logger.exception(f"Error parsing the response: {e}")
    return list(selected_nodes)


def link_by_passage_node(hipporag: HippoRAG, query: str, link_top_k: Union[None, int]):
    query_embedding = hipporag.embed_model.encode_text(query, instruction=get_query_instruction(hipporag.embed_model, 'query_to_passage', hipporag.corpus_name),
                                                       return_cpu=True, return_numpy=True, norm=True)
    query_doc_scores = np.dot(hipporag.doc_embedding_mat, query_embedding.T)  # (num_docs, dim) x (1, dim).T = (num_docs, 1)
    query_doc_scores = np.squeeze(query_doc_scores)

    top_doc_idx = np.argsort(query_doc_scores)[-10:][::-1].tolist()

    docs = []
    doc_scores = []
    phrases_by_doc = []
    all_candidate_phrases = set()
    for doc_idx in top_doc_idx:
        doc = hipporag.get_passage_by_idx(doc_idx)
        phrases = hipporag.get_phrase_in_doc_by_idx(doc_idx)
        docs.append(doc)
        phrases_by_doc.append(phrases)
        doc_scores.append(query_doc_scores[doc_idx])
        all_candidate_phrases.update([p.lower() for p in phrases])

    assert len(docs) == len(phrases_by_doc)
    selected_nodes = generate_nodes(hipporag, query, docs, phrases_by_doc)

    all_phrase_weights = np.zeros(len(hipporag.node_phrases))
    linking_score_map = {}
    if len(selected_nodes) == 0:
        selected_nodes = difflib.get_close_matches(query, all_candidate_phrases, n=5, cutoff=0.0)
    elif link_top_k is not None and len(selected_nodes) > link_top_k:
        # keep top k selected nodes which have the highest linking scores
        ratios = []
        for phrase in selected_nodes:
            closest_match = difflib.get_close_matches(phrase, all_candidate_phrases, n=1, cutoff=0.0)[0]
            ratio = difflib.SequenceMatcher(None, phrase, closest_match).ratio()
            ratios.append(ratio)
        # sort by ratios in descending order and keep top k
        selected_nodes = [x for _, x in sorted(zip(ratios, selected_nodes), reverse=True)][:link_top_k]

    for phrase in selected_nodes:
        # choose the most similar phrase from phrases_by_doc
        closest_match = difflib.get_close_matches(phrase, all_candidate_phrases, n=1, cutoff=0)[0]

        phrase_id = hipporag.kb_node_phrase_to_id.get(closest_match, None)
        if phrase_id is None:
            hipporag.logger.error(f'Phrase {phrase} not found in the KG')
            continue
        if hipporag.node_specificity:
            if hipporag.phrase_to_num_doc[phrase_id] == 0:
                weight = 1
            else:
                weight = 1 / hipporag.phrase_to_num_doc[phrase_id]
            all_phrase_weights[phrase_id] = weight
        else:
            all_phrase_weights[phrase_id] = 1.0

        for p in phrases_by_doc:
            if phrase in p:
                linking_score_map[phrase_id] = doc_scores[phrases_by_doc.index(p)]
                break

    assert sum(all_phrase_weights) > 0, f"Phrase weights are all zeros: {all_phrase_weights}"
    sorted_doc_ids, sorted_scores, logs = graph_search_with_entities(hipporag, all_phrase_weights, linking_score_map, query_doc_scores=query_doc_scores)

    logs['llm_selected_nodes'] = selected_nodes
    return sorted_doc_ids, sorted_scores, logs
