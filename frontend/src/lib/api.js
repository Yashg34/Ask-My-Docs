export const api = async (path, options = {}) => {
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: options.body instanceof FormData
      ? options.headers
      : { 'Content-Type': 'application/json', ...options.headers },
  });

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error(
      `Server returned ${response.status}: expected JSON, got "${contentType || 'unknown content-type'}". ` +
      `Check that ${path} is reaching the backend (proxy/route misconfiguration is a common cause).`
    );
  }

  const payload = await response.json().catch(() => {
    throw new Error(`Server returned ${response.status} with malformed JSON from ${path}.`);
  });
  if (!response.ok) throw new Error(payload.error?.message || 'Something went wrong.');
  return payload;
};