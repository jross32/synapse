// Shared "needs review" count for nav badges. Counts work-item handoffs/blocked
// items plus open AI-filed proposals, and refreshes live on the review + work-item
// events the daemon already broadcasts, so the nav lights up the moment an AI hands
// work back or files an idea (instead of it piling up unseen inside a buried tab).

import { useCallback, useEffect, useState } from 'react';

import { getReviewInbox } from './review-client';
import { useDaemon } from './daemon-context';

export function useReviewCount(): number {
  const { subscribeRaw, connState } = useDaemon();
  const [count, setCount] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const inbox = await getReviewInbox();
      setCount((inbox.count ?? 0) + (inbox.proposals?.length ?? 0));
    } catch {
      // Keep the last known count on a transient error rather than flashing to 0.
    }
  }, []);

  useEffect(() => {
    if (connState !== 'open') return;
    void refresh();
  }, [connState, refresh]);

  useEffect(
    () =>
      subscribeRaw((event) => {
        if (
          event.name === 'v1.review.resolved' ||
          event.name === 'v1.review.proposal_filed' ||
          event.name.startsWith('v1.agent_work_item')
        ) {
          void refresh();
        }
      }),
    [subscribeRaw, refresh]
  );

  return count;
}
