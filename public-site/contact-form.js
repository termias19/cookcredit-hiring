(() => {
 const form = document.getElementById('contact-form');
 if (!form) return;
 const status = document.getElementById('contact-status');
 const button = form.querySelector('button[type="submit"]');
 let requestId = crypto.randomUUID();
 form.addEventListener('input', () => { if (!button.disabled) requestId = crypto.randomUUID(); });
 form.addEventListener('submit', async event => {
  event.preventDefault();
  if (button.disabled || !form.reportValidity()) return;
  const data = Object.fromEntries(new FormData(form));
  data.requestId = requestId;
  const fields = [...form.querySelectorAll('input, textarea')];
  fields.forEach(field => { field.disabled = true; });
  button.disabled = true; button.textContent = 'Sending…'; status.textContent = '';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
   const response = await fetch(form.dataset.endpoint, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal,credentials:'omit'});
   const result = await response.json();
   if (!response.ok || result.sent !== true) throw new Error(result.error || 'We could not confirm delivery. Please try later or email connectwithus@cookcredit.com.');
   status.textContent = 'Your message has been sent to CookCredit. Thank you.';
   form.reset(); requestId = crypto.randomUUID();
  } catch (error) {
   status.textContent = error.name === 'AbortError' || error instanceof TypeError ? 'We could not confirm delivery. Your message is still here. Please try later or email connectwithus@cookcredit.com.' : error.message;
  } finally {
   clearTimeout(timeout); fields.forEach(field => { field.disabled = false; }); button.disabled = false; button.textContent = 'Send message'; status.focus();
  }
 });
})();
