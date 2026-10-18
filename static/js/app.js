// Small enhancements only; everything works without JavaScript.
(function () {
  var nav = document.getElementById('nav');
  document.querySelectorAll('[data-toggle="nav"]').forEach(function (b) {
    b.addEventListener('click', function () { nav.classList.toggle('open'); });
  });

  // Pack-size price display
  var target = document.querySelector('[data-price-target]');
  document.querySelectorAll('input[name="sku"]').forEach(function (r) {
    r.addEventListener('change', function () {
      if (target) target.textContent = '₹' + Number(r.dataset.price).toLocaleString('en-IN');
    });
  });

  // Quantity stepper
  document.querySelectorAll('[data-step]').forEach(function (b) {
    b.addEventListener('click', function () {
      var input = b.parentElement.querySelector('input');
      var v = Math.min(20, Math.max(1, (parseInt(input.value, 10) || 1) + Number(b.dataset.step)));
      input.value = v;
    });
  });
})();
