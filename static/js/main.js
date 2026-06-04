// KongoAnnonces — main.js

document.addEventListener('DOMContentLoaded', function() {

  // Active city pill on homepage
  const pills = document.querySelectorAll('.city-pill');
  pills.forEach(pill => {
    pill.addEventListener('click', function(e) {
      pills.forEach(p => p.classList.remove('active'));
      this.classList.add('active');
    });
  });

  // Auto-dismiss flash messages
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach(f => {
    setTimeout(() => {
      f.style.opacity = '0';
      f.style.transition = 'opacity .4s';
      setTimeout(() => f.remove(), 400);
    }, 4000);
  });

});
