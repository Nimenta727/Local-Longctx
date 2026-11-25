import { isReplacementSurfaceEvent, type Session, type SessionSeq } from '@deepseek-ai/dsh-session'

/** Follow only predecessors of replacements visible on the current session branch. */
export function archiveSources(session: Session, seq: SessionSeq): readonly SessionSeq[] {
  const event = session.eventAt(seq)
  if (!event || !isReplacementSurfaceEvent(event)) return []
  const refs = event.sourceEventSeqs ?? []
  return event.type === 'tool/result' || refs.some(ref => session.eventAt(ref)?.type === 'compaction/summary')
    ? refs : []
}
