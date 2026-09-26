firebase.initializeApp({
  apiKey: "AIzaSyAHVJ-y1JkGTWUA-ONEpPWQ0KWQ08YHyX8",
  authDomain: "foodnlit-1123e.firebaseapp.com",
  projectId: "foodnlit-1123e",
  storageBucket: "foodnlit-1123e.firebasestorage.app",
  messagingSenderId: "319305393408",
  appId: "1:319305393408:web:156dd95582a241938ebfe5"
});

var db = firebase.firestore();

// Rate limiting: 1 submission per 60 seconds
var lastSubmitTime = 0;
var RATE_LIMIT_MS = 60000;

function showToast(msg) {
  var el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(function() { el.classList.remove('show'); }, 5000);
}

function isRateLimited() {
  var now = Date.now();
  if (now - lastSubmitTime < RATE_LIMIT_MS) {
    var secsLeft = Math.ceil((RATE_LIMIT_MS - (now - lastSubmitTime)) / 1000);
    showToast('Please wait ' + secsLeft + 's before submitting again.');
    return true;
  }
  return false;
}

function checkDuplicate(email) {
  return db.collection('waitlist')
    .where('email', '==', email.toLowerCase())
    .limit(1)
    .get()
    .then(function(snap) {
      return !snap.empty;
    });
}

function submitEmail(email, role) {
  var normalized = email.toLowerCase().trim();
  return checkDuplicate(normalized).then(function(exists) {
    if (exists) {
      showToast('This email is already on the waitlist.');
      return Promise.reject('duplicate');
    }
    lastSubmitTime = Date.now();
    return db.collection('waitlist').add({
      email: normalized,
      role: role || 'general',
      timestamp: firebase.firestore.FieldValue.serverTimestamp(),
      source: window.location.href
    });
  });
}

var heroForm = document.getElementById('hero-form');
if (heroForm) {
  heroForm.addEventListener('submit', function(e) {
    e.preventDefault();
    if (isRateLimited()) return;
    var input = e.target.querySelector('input[type="email"]');
    var btn = e.target.querySelector('button');
    var email = input.value.trim();
    if (!email) return;
    btn.disabled = true;
    btn.textContent = 'Sending...';
    submitEmail(email, 'general').then(function() {
      showToast('You are on the list. Reach out to info@cookcredit.com with questions.');
      input.value = '';
    }).catch(function(err) {
      if (err !== 'duplicate') showToast('Something went wrong. Try again.');
    }).finally(function() {
      btn.disabled = false;
      btn.textContent = 'Join the waitlist';
    });
  });
}

var mForm = document.getElementById('marketplace-form');
if (mForm) {
  mForm.addEventListener('submit', function(e) {
    e.preventDefault();
    if (isRateLimited()) return;
    var input = e.target.querySelector('input[type="email"]');
    var select = e.target.querySelector('select');
    var btn = e.target.querySelector('button');
    var email = input.value.trim();
    var role = select.value;

    if (!email || !role) {
      showToast('Please fill in all fields.');
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Sending...';

    submitEmail(email, role).then(function() {
      showToast('You are on the list. Reach out to info@cookcredit.com with questions.');
      input.value = '';
      select.selectedIndex = 0;
    }).catch(function(err) {
      if (err !== 'duplicate') showToast('Something went wrong. Try again.');
    }).finally(function() {
      btn.disabled = false;
      btn.textContent = 'Sign up';
    });
  });
}

// Dynamic media loader
var MEDIA = [];

function loadMedia() {
  MEDIA.forEach(function(m) {
    var slot = document.querySelector('.media-slot[data-slot="' + m.slot + '"]');
    if (!slot) return;
    slot.innerHTML = '';
    if (m.type === 'video') {
      var v = document.createElement('video');
      v.autoplay = true;
      v.muted = true;
      v.loop = true;
      v.playsInline = true;
      if (m.poster) v.poster = m.poster;
      v.src = m.src;
      slot.appendChild(v);
    } else {
      var img = document.createElement('img');
      img.src = m.src;
      img.alt = m.alt || '';
      img.loading = 'lazy';
      slot.appendChild(img);
    }
  });
  document.querySelectorAll('.media-slot').forEach(function(s) {
    if (!s.querySelector('video') && !s.querySelector('img')) {
      s.style.display = 'none';
    }
  });
  var grid = document.querySelector('.media-grid');
  if (grid && grid.querySelectorAll('.media-slot:not([style*="display: none"])').length === 0) {
    grid.classList.add('empty');
  }
}

loadMedia();
