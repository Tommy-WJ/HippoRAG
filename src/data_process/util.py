import hashlib


def chunk_corpus(corpus: list, chunk_size: int = 64) -> list:
    """
    Chunk the corpus into smaller parts. Run the following command to download the required nltk data:
    python -c "import nltk; nltk.download('punkt')"

    @param corpus: the formatted corpus, see README.md
    @param chunk_size: the size of each chunk, i.e., the number of words in each chunk
    @return: chunked corpus, a list
    """
    from nltk.tokenize import sent_tokenize, word_tokenize

    new_corpus = []
    for p in corpus:
        text = p['text']
        idx = p['idx'] if 'idx' in p else p['_id']
        title = p['title']

        sentences = sent_tokenize(text)
        current_chunk = []
        current_chunk_size = 0

        chunk_idx = 0
        for sentence in sentences:
            words = word_tokenize(sentence)
            if current_chunk_size + len(words) > chunk_size:
                new_corpus.append({
                    **p,
                    'title': title,
                    'text': " ".join(current_chunk),
                    'idx': idx + f"_{chunk_idx}",
                })
                current_chunk = words
                current_chunk_size = len(words)
                chunk_idx += 1
            else:
                current_chunk.extend(words)
                current_chunk_size += len(words)

        if current_chunk:  # there are still some words left
            new_corpus.append({
                **p,
                'title': title,
                'text': " ".join(current_chunk),
                'idx': f"{idx}_{chunk_idx}",
            })

    return new_corpus


def merge_chunk_scores(id_score: dict):
    """
    Merge the scores of chunks into the original passage
    @param id_score: a dictionary of passage_id (the chunk id, str) -> score (float)
    @return: a merged dictionary of passage_id (the original passage id, str) -> score (float)
    """
    merged_scores = {}
    for passage_id, score in id_score.items():
        passage_id = passage_id.split('_')[0]
        if passage_id not in merged_scores:
            merged_scores[passage_id] = 0
        merged_scores[passage_id] = max(merged_scores[passage_id], score)
    return merged_scores


def merge_chunks(corpus: list):
    """
    Merge the chunks of a corpus into the original passage
    @param corpus: a passage list
    @return: a merged corpus, dict
    """

    new_corpus = {}
    for p in corpus:
        idx = p['idx']
        if '_' not in idx:
            new_corpus[idx] = p
        else:
            original_idx = idx.split('_')[0]
            if original_idx not in new_corpus:
                new_corpus[original_idx] = {
                    **p,
                    'text': p['text'],
                    'idx': original_idx,
                }
            else:
                new_corpus[original_idx]['text'] += ' ' + p['text']

    return list(new_corpus.values())


def generate_hash(input_string, algorithm='sha224'):
    import hashlib
    try:
        algo = getattr(hashlib, algorithm)()
    except AttributeError:
        raise ValueError(f'Unsupported algorithm: {algorithm}')
    algo.update(input_string.encode('utf-8'))
    return algo.hexdigest()


def check_continuity(data):
    sorted_values = [v for k, v in data.items()]

    breaks = []
    continuous_ranges = []
    start = 0

    for i in range(1, len(sorted_values)):
        if sorted_values[i] != sorted_values[i - 1] + 1:
            breaks.append(i)
            continuous_ranges.append((sorted_values[start], sorted_values[i - 1]))
            start = i

    continuous_ranges.append((sorted_values[start], sorted_values[-1]))

    if len(breaks) > 0:
        print(f"Breaks at indices: {breaks}")
        print(f"Number of continuous subarrays: {len(continuous_ranges)}")
        print(f"Continuous ranges (start, end): {continuous_ranges}")
        exit(1)
