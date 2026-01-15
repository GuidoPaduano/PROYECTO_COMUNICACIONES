export function notifyInboxChanged() {
  // storage event (entre pestañas)
  try {
    localStorage.setItem("inbox:lastChange", String(Date.now()))
  } catch {}

  // BroadcastChannel si existe
  try {
    // @ts-ignore
    if ("BroadcastChannel" in window) {
      // @ts-ignore
      const bc = new BroadcastChannel("inbox")
      bc.postMessage({ type: "changed", ts: Date.now() })
      bc.close()
    }
  } catch {}
}
