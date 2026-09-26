// Highlight only known navigation destinations. URL input is never rendered as HTML.
(() => {
  const normalize = (path) => path.replace(/\/index\.html$/, '/').replace(/\/+$/, '') || '/';
  const path = normalize(location.pathname);
  const links = [...document.querySelectorAll('.site-nav a, .footer-links a')];
  const samePage = links.map(link => ({link, url: new URL(link.href)}))
    .filter(({url}) => url.origin === location.origin && normalize(url.pathname) === path);
  samePage.filter(({url}) => !url.hash).forEach(({link}) => link.setAttribute('aria-current', 'page'));
  const sections = samePage.filter(({link,url}) => url.hash && link.closest('.site-nav'))
    .map(({link,url}) => ({link, section: document.getElementById(url.hash.slice(1))}))
    .filter(({section}) => section);
  if (!sections.length) return;
  let queued = false;
  const update = () => {
    queued = false;
    let active;
    for (const item of sections) {
      if (item.section.getBoundingClientRect().top <= innerHeight * 0.35) active = item;
    }
    for (const item of sections) {
      if (item === active) item.link.setAttribute('aria-current', 'location');
      else item.link.removeAttribute('aria-current');
    }
  };
  const schedule = () => { if (!queued) { queued = true; requestAnimationFrame(update); } };
  addEventListener('scroll', schedule, {passive:true});
  addEventListener('resize', schedule);
  addEventListener('hashchange', schedule);
  addEventListener('pageshow', schedule);
  update();
})();
