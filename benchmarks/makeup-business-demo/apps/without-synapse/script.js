document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('contact-form');
  var successMsg = document.getElementById('form-success');

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    successMsg.classList.remove('hidden');
    form.reset();
  });
});
