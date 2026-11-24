/* Animaciones del Resumen (identidad Integra):
   - .revelar: los bloques que están fuera de pantalla aparecen suavemente al bajar;
   - .ruta-vertical: la línea se llena de amarillo con el scroll y enciende un nodo por sección (.nodo-ruta).
   Dash arma la página después de cargar, así que se vigila el DOM para activar lo que vaya apareciendo.
   Con «reducir movimiento» activado en el sistema no se anima nada. */
(function () {
  var reducir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducir || !('IntersectionObserver' in window)) return;

  var io = new IntersectionObserver(function (entradas) {
    entradas.forEach(function (e) {
      if (e.isIntersecting) { e.target.classList.remove('pre'); io.unobserve(e.target); }
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });

  function preparar() {
    var vh = window.innerHeight;
    document.querySelectorAll('.revelar:not([data-rev])').forEach(function (el) {
      el.setAttribute('data-rev', '1');
      if (el.getBoundingClientRect().top > vh * 0.92) { el.classList.add('pre'); io.observe(el); }
    });
    armarRuta();
  }

  var ruta = null, nodos = [], secciones = [];
  function armarRuta() {
    var r = document.querySelector('.ruta-vertical');
    if (r === ruta && r && nodos.length) { mover(); return; }
    ruta = r; nodos = []; secciones = [];
    if (!ruta) return;
    secciones = Array.prototype.slice.call(document.querySelectorAll('.nodo-ruta'));
    ruta.querySelectorAll('b').forEach(function (b) { b.remove(); });
    secciones.forEach(function () { var b = document.createElement('b'); ruta.appendChild(b); nodos.push(b); });
    mover();
  }

  function mover() {
    if (!ruta || !ruta.isConnected) return;
    var alto = document.documentElement.scrollHeight - window.innerHeight;
    var p = alto > 0 ? Math.min(1, Math.max(0, window.scrollY / alto)) : 0;
    ruta.style.setProperty('--p', p);
    var vh = window.innerHeight;
    secciones.forEach(function (s, i) {
      // posición del nodo en la línea, proporcional a dónde está la sección en la página
      var y = (s.getBoundingClientRect().top + window.scrollY) / Math.max(1, document.documentElement.scrollHeight) * vh;
      nodos[i].style.top = y + 'px';
      nodos[i].classList.toggle('on', p * vh >= y - 1);
    });
  }

  var pendiente = false;
  function alBajar() {
    if (pendiente) return;
    pendiente = true;
    requestAnimationFrame(function () { pendiente = false; mover(); });
  }
  window.addEventListener('scroll', alBajar, { passive: true });
  window.addEventListener('resize', alBajar);

  new MutationObserver(function () { preparar(); }).observe(document.body, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', preparar);
})();
