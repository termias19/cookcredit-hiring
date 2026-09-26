(() => {
  'use strict'
  const script = document.currentScript
  if (!script || script.dataset.cookcreditMounted === '1') return
  script.dataset.cookcreditMounted = '1'
  const roleId = script.dataset.role || ''
  const publicKey = script.dataset.key || ''
  const apiOrigin = (script.dataset.api || 'https://cookcredit-api-eqqoi6wp6a-uc.a.run.app').replace(/\/$/, '')
  const appOrigin = (script.dataset.app || 'https://cookcredit.com').replace(/\/$/, '')
  const root = document.createElement('div')
  root.setAttribute('data-cookcredit-widget', roleId)
  script.insertAdjacentElement('afterend', root)
  const shadow = root.attachShadow({ mode: 'closed' })

  const safeText = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character])
  const renderError = message => {
    shadow.innerHTML = `<div role="status" style="font:14px system-ui;color:#6b625d;border:1px solid #ddd8d0;padding:16px">${safeText(message)}</div>`
  }
  if (!/^[0-9a-f-]{36}$/i.test(roleId) || !/^pk_[A-Za-z0-9_-]{20,}$/.test(publicKey)) { renderError('CookCredit widget is not configured.'); return }

  fetch(`${apiOrigin}/api/embed/v1/${encodeURIComponent(publicKey)}/roles/${encodeURIComponent(roleId)}`, { mode: 'cors', credentials: 'omit' })
    .then(response => response.ok ? response.json() : Promise.reject(new Error('Role unavailable')))
    .then(({ role }) => {
      const color = /^#[0-9a-f]{6}$/i.test(role.company?.brandColor || '') ? role.company.brandColor : '#1F6F5C'
      const pay = role.employment?.payMin != null && role.employment?.payMax != null
        ? `$${role.employment.payMin}–$${role.employment.payMax} / hour` : 'Pay shown in application'
      const logo = role.company?.logoUrl ? `<img src="${safeText(encodeURI(role.company.logoUrl))}" alt="" referrerpolicy="no-referrer" />` : ''
      shadow.innerHTML = `<style>
        :host{all:initial}.cc{box-sizing:border-box;border:1px solid #ddd8d0;background:#fff;color:#1a1a1a;padding:22px;max-width:620px;font:14px/1.5 Inter,system-ui,sans-serif}.head{display:flex;gap:12px;align-items:center}.head img{width:42px;height:42px;object-fit:contain}.company{font-size:11px;letter-spacing:1.7px;text-transform:uppercase;color:#777}.title{font:400 29px/1.1 Georgia,serif;margin:12px 0 8px}.meta{color:#666;margin:0 0 18px}.apply{display:inline-flex;background:${color};color:#fff!important;text-decoration:none;padding:12px 19px;font-weight:650}.foot{font-size:10px;color:#999;margin:12px 0 0}.apply:focus{outline:3px solid ${color}55;outline-offset:3px}</style>
        <section class="cc" aria-label="${safeText(role.title)} at ${safeText(role.company?.name)}">
          <div class="head">${logo}<div class="company">${safeText(role.company?.name)}</div></div>
          <div class="title">${safeText(role.title)}</div>
          <p class="meta">${safeText(role.location?.label || role.company?.city || '')} · ${safeText(role.employment?.type || '')}<br>${safeText(pay)}</p>
          <a class="apply" href="${appOrigin}/apply/${encodeURIComponent(role.id)}" target="_blank" rel="noopener">Apply with CookCredit</a>
          <p class="foot">The application and existing camera assessment open securely on CookCredit. The employer makes the hiring decision.</p>
        </section>`
    })
    .catch(() => renderError('This CookCredit role is unavailable.'))
})()
