function focusUrlAllowed(rawUrl, policy) {
  try {
    const url = new URL(rawUrl);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
        (url.port && !((url.protocol === "https:" && url.port === "443") || (url.protocol === "http:" && url.port === "80")))) return false;
    if (!policy) return false;
    if (!policy.session_id || !policy.active) return true; // no session or paused: enforcement is suspended
    if (policy.mode !== "controlled_browser") return false;
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    return (policy.domains || []).some((item) => item.startsWith("*.")
      ? host.endsWith(`.${item.slice(2)}`)
      : host === item);
  } catch { return false; }
}

module.exports = { focusUrlAllowed };
