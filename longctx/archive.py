"""Search original assistant messages removed by managed compaction."""
import re

# Split code identifiers at punctuation. Index overlapping CJK pairs so prose
# without spaces can be retrieved with SQLite's unicode61 tokenizer.
WORDS = re.compile(r"[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+")
CJK = re.compile(r"[\u3400-\u9fff]+")


def terms(text):
    for match in WORDS.finditer(text):
        word = match[0]
        if len(word) > 1 and CJK.fullmatch(word):
            yield from (word[i:i + 2] for i in range(len(word) - 1))
        else:
            yield word


def passages(content):
    offset = 0
    for line in content.splitlines(keepends=True):
        end = offset + len(line)
        for start in range(offset, end, 640):
            stop = min(start + 768, end)
            yield start, stop, content[start:stop]
            if stop == end:
                break
        offset = end


def index_compaction(db, sid, revision, source_revision, before, after):
    for index, (original, replacement) in enumerate(zip(before, after)):
        if original == replacement or original["role"] != "assistant":
            continue
        content = original["content"]
        rows = (
            (sid, revision, source_revision, index, start, stop, " ".join(terms(passage)))
            for start, stop, passage in passages(content)
            if passage.strip() and passage.strip() not in replacement["content"]
        )
        db.executemany(
            "INSERT INTO archive_search(sid, revision, source_revision, message_index, start, stop, words) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", rows,
        )
    db.execute("INSERT INTO archive_indexed VALUES (?, ?)", (sid, revision))


def search(db, sid, revision, query, read):
    keywords = list(dict.fromkeys(terms(query)))[:64]
    if not keywords:
        return []
    # New rollbacks point to their restored revision. Older databases stored
    # the previous head instead. Stop at those rollback boundaries, since the
    # exact target cannot be recovered from the snapshot alone.
    lineage = """
        WITH RECURSIVE lineage(rev, parent, action, sha) AS (
            SELECT rev, parent, action, sha FROM revisions WHERE sid=? AND rev=?
            UNION ALL
            SELECT r.rev, r.parent, r.action, r.sha
            FROM revisions r JOIN lineage l ON r.rev=l.parent
            WHERE r.sid=? AND (l.action!='rollback' OR r.sha=l.sha)
        )
    """
    args = (sid, revision, sid)
    missing = db.execute(
        lineage + "SELECT rev, parent FROM lineage WHERE action='compact' AND "
        "NOT EXISTS (SELECT 1 FROM archive_indexed i WHERE i.sid=? AND i.rev=lineage.rev)",
        (*args, sid),
    ).fetchall()
    for compacted, source in missing:
        index_compaction(db, sid, compacted, source,
                         read(sid, source)["messages"], read(sid, compacted)["messages"])
    expression = " OR ".join(f'"{term}"' for term in keywords)
    rows = db.execute(
        lineage + "SELECT a.source_revision, a.message_index, a.start, a.stop FROM archive_search a "
        "JOIN lineage l ON a.revision=l.rev WHERE a.sid=? AND archive_search MATCH ? "
        "ORDER BY bm25(archive_search), a.revision DESC, a.message_index, a.start LIMIT 32",
        (*args, sid, expression),
    ).fetchall()
    originals = {}
    hits = []
    for source, index, start, stop in rows:
        if source not in originals:
            originals[source] = read(sid, source)["messages"]
        hits.append({"revision": source, "index": index, "start": start, "end": stop,
                     "content": originals[source][index]["content"][start:stop]})
    return hits
