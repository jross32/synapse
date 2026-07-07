'use strict';

let subscriberCount = 0;

function subscribe() {
  var name = document.getElementById('sub-name').value;
  // BUG B11: the "non-empty" gate uses .length without .trim(), so a
  // whitespace-only name ("   ") passes as a real subscriber.
  if (name.length > 0) {
    // BUG B03: no guard against double-submit — clicking Subscribe twice
    // counts the same person twice (and re-shows the message each time).
    subscriberCount += 1;
    document.getElementById('sub-count').textContent = String(subscriberCount);
    document.getElementById('sub-msg').classList.remove('hidden');
  }
}

function sendMessage() {
  var name = document.getElementById('c-name').value;
  // BUG B01: nothing is validated. Empty name / email / message all "succeed".
  // BUG B02: email is never checked for a valid format.
  var confirm = document.getElementById('c-confirm');
  // BUG B12: the user-supplied name is injected via innerHTML with no escaping —
  // reflected XSS. A name of `<img src=x onerror=alert(1)>` executes.
  confirm.innerHTML = 'Thanks, ' + name + '! Your message was sent.';
  confirm.classList.remove('hidden');
}
