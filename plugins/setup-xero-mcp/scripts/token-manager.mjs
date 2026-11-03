/** Refresh in memory; Python persists rotation under its OS lock. */
export function createTokenManager(refresh, {
  now = Date.now, schedule = setTimeout, cancel = clearTimeout, onToken = () => {},
  onError = () => console.error('Xero token refresh failed; retrying automatically. Reauthorize if persistent.')
} = {}) {
  let current, pending, timer, closed = false;
  let refreshAt = 0, expiresAt = 0;
  function arm(delay) {
    if (closed) return;
    if (timer) cancel(timer);
    timer = schedule(() => {
      timer = undefined;
      obtain(true).catch(() => {});
    }, delay);
    timer?.unref?.();
  }
  async function obtain(force = false) {
    if (closed) throw new Error('Xero token manager stopped.');
    if (pending) return pending;
    if (!force && current && now() < refreshAt) return current;
    // One refresh per process, including concurrent tool calls and timer ticks.
    pending = (async () => {
      try {
        const started = now();
        const result = await refresh();
        const lifetime = Number(result.expires_in) * 1000;
        if (typeof result.access_token !== 'string' || !result.access_token ||
            !Number.isFinite(lifetime) || lifetime <= 0 || lifetime > 86400000) {
          throw new Error('Invalid token response.');
        }
        expiresAt = started + lifetime;
        refreshAt = expiresAt - Math.min(120000, lifetime / 2);
        if (now() >= expiresAt) throw new Error('Token expired during refresh.');
        current = { access_token: result.access_token, expires_at: expiresAt / 1000,
                    token_type: 'Bearer' };
        onToken(current);
        arm(Math.max(1, refreshAt - now()));
        return current;
      } catch {
        arm(10000);
        onError();
        // Existing token remains usable during transient network failure, but
        // never let an expired token through. No Xero API operation is replayed.
        if (current && now() < expiresAt) return current;
        throw new Error('Xero authorization unavailable; automatic refresh will retry. Reauthorize if persistent.');
      } finally {
        pending = undefined;
      }
    })();
    try { return await pending; }
    finally { pending = undefined; }
  }
  return { getToken: () => obtain(), close() {
    closed = true;
    if (timer) cancel(timer);
  } };
}
