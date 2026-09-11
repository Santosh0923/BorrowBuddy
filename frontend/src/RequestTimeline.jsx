import { useState } from 'react';
import { timestamp } from './api';
import { compactHistory, presentHistory } from './requestHistory';

export function RequestTimeline({ history, role }) {
  const [expanded, setExpanded] = useState(false);
  const events = presentHistory(history, role);
  const visible = expanded ? events : compactHistory(events);
  if (!events.length) return <p className="muted small">No activity is available for this request yet.</p>;
  return <>
    <ol className="timeline" aria-label="Request activity">
      {visible.map((event, index) => <li key={`${event.date}-${index}`}><span className="timeline-dot" /><div>
        <strong>{event.title}</strong>
        <small>{timestamp(event.date)}{event.actor && <> · {event.actor}</>}</small>
        {event.note && <p>{event.note}</p>}
        {event.reason && <p>Reason: {event.reason}</p>}
      </div></li>)}
    </ol>
    {events.length > 6 && <button type="button" className="button text-button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? 'Show less' : 'View full history'}</button>}
  </>;
}
