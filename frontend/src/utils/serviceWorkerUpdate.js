/** Offer a waiting release; only this tab's explicit acceptance may reload it. */
export function watchForAppUpdate({ serviceWorker, onReady, onUnavailable, reload }) {
  if (!serviceWorker) return () => {}
  let disposed = false
  let registration
  let installing
  let accepted = false
  let activationTimer
  let previousController = serviceWorker.controller

  function applyUpdate() {
    if (disposed || accepted) return
    accepted = true
    if (!registration?.waiting) {
      // Another tab may already have activated the release after our prompt appeared.
      reload()
      return
    }
    activationTimer = setTimeout(() => {
      accepted = false
      onUnavailable()
    }, 15000)
    try {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' })
    } catch {
      clearTimeout(activationTimer)
      accepted = false
      onUnavailable()
    }
  }

  function offerWaitingUpdate() {
    if (!disposed && serviceWorker.controller && registration?.waiting) onReady(applyUpdate)
  }

  function watchInstallingWorker() {
    installing?.removeEventListener('statechange', offerWaitingUpdate)
    installing = registration.installing
    installing?.addEventListener('statechange', offerWaitingUpdate)
    offerWaitingUpdate()
  }

  function controllerChanged() {
    const wasControlled = Boolean(previousController)
    previousController = serviceWorker.controller
    if (disposed || !previousController) return
    if (accepted) {
      clearTimeout(activationTimer)
      accepted = false
      reload()
    } else if (wasControlled) {
      // Do not reload another tab's unsaved application when one tab accepts an update.
      onReady(applyUpdate)
    }
  }

  serviceWorker.addEventListener('controllerchange', controllerChanged)
  serviceWorker.register('/sw.js', { updateViaCache: 'none' }).then(reg => {
    if (disposed) return
    registration = reg
    reg.addEventListener('updatefound', watchInstallingWorker)
    watchInstallingWorker()
    // register() can return an existing registration without a fresh fetch.
    // Explicitly check once per page load; acceptance still controls reload.
    Promise.resolve(reg.update?.()).catch(() => { if (!disposed) onUnavailable() })
  }).catch(() => { if (!disposed) onUnavailable() })

  return () => {
    disposed = true
    clearTimeout(activationTimer)
    serviceWorker.removeEventListener('controllerchange', controllerChanged)
    registration?.removeEventListener('updatefound', watchInstallingWorker)
    installing?.removeEventListener('statechange', offerWaitingUpdate)
  }
}
