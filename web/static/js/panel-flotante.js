/* panel-flotante.js — Paneles flotantes reutilizables para CHP App
 * Uso: abrirPanel('id-del-panel')
 * Estructura HTML esperada:
 *   <div class="panel-flotante" id="...">
 *     <div class="panel-header">
 *       <span class="panel-titulo">Título</span>
 *       <button class="panel-cerrar">×</button>
 *     </div>
 *     <div class="panel-body">...</div>
 *     <div class="panel-resize"></div>
 *   </div>
 */

class PanelFlotante {
  static _zBase  = 1050;
  static _zCount = 0;
  static _openCount = 0;   // para calcular offset en cascada

  constructor(id) {
    this.el = document.getElementById(id);
    if (!this.el) { console.warn('PanelFlotante: no se encontró #' + id); return; }
    this._initClose();
    this._initDrag();
    this._initResize();
    this._initFocus();
  }

  /** Mide la altura necesaria para mostrar todo el contenido (cap 95% viewport). */
  _medirAltura() {
    const header = this.el.querySelector('.panel-header');
    const body   = this.el.querySelector('.panel-body');
    const resize = this.el.querySelector('.panel-resize');
    const altoMax = Math.round(window.innerHeight * 0.95);
    const natural = (header ? header.offsetHeight : 0)
                  + (body   ? body.scrollHeight   : 0)
                  + (resize ? resize.offsetHeight : 0);
    return Math.min(natural || altoMax, altoMax);
  }

  /** Abre el panel. Si ya está visible, lo trae al frente. */
  abrir() {
    if (!this.el) return;
    if (this.el.style.display === 'flex') {
      this.traerAlFrente();
      return;
    }

    const w = Math.round(window.innerWidth * 0.95);

    // Mostrar primero para que el DOM esté renderizado al medir
    this.el.style.width   = w + 'px';
    this.el.style.display = 'flex';

    const h = this._medirAltura();

    const idx    = PanelFlotante._openCount % 7;
    const offset = idx * 30;
    const rawL   = (window.innerWidth  - w) / 2 + offset;
    const rawT   = (window.innerHeight - h) / 2 + offset;
    const left   = Math.min(Math.max(0, rawL), window.innerWidth  - 120);
    const top    = Math.min(Math.max(0, rawT),  window.innerHeight - 60);

    this.el.style.left   = left + 'px';
    this.el.style.top    = top  + 'px';
    this.el.style.height = h    + 'px';

    PanelFlotante._openCount++;
    this.traerAlFrente();
  }

  /**
   * Reajusta la altura del panel al contenido actual.
   * Llamar tras cargar datos dinámicos en el panel-body.
   */
  ajustarAltura() {
    if (!this.el || this.el.style.display !== 'flex') return;
    const h   = this._medirAltura();
    const top = Math.min(
      Math.max(0, this.el.offsetTop),
      window.innerHeight - 60
    );
    this.el.style.top    = top + 'px';
    this.el.style.height = h   + 'px';
  }

  /** Cierra el panel. */
  cerrar() {
    if (!this.el) return;
    this.el.style.display = 'none';
    PanelFlotante._openCount = Math.max(0, PanelFlotante._openCount - 1);
  }

  /** Trae el panel al frente incrementando su z-index. */
  traerAlFrente() {
    if (!this.el) return;
    PanelFlotante._zCount++;
    this.el.style.zIndex = PanelFlotante._zBase + PanelFlotante._zCount;
  }

  _initClose() {
    const btn = this.el.querySelector('.panel-cerrar');
    if (!btn) return;
    btn.addEventListener('click', (e) => { e.preventDefault(); this.cerrar(); });
  }

  _initDrag() {
    const header = this.el.querySelector('.panel-header');
    if (!header) return;

    header.addEventListener('mousedown', (e) => {
      if (e.target.closest('.panel-cerrar')) return;
      e.preventDefault();
      const startX = e.clientX;
      const startY = e.clientY;
      const startL = this.el.offsetLeft;
      const startT = this.el.offsetTop;
      this.traerAlFrente();

      const onMove = (e) => {
        const newL = Math.max(0, Math.min(window.innerWidth  - 120, startL + e.clientX - startX));
        const newT = Math.max(0, Math.min(window.innerHeight - 40,  startT + e.clientY - startY));
        this.el.style.left = newL + 'px';
        this.el.style.top  = newT + 'px';
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup',   onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup',   onUp);
    });
  }

  _initResize() {
    const handle = this.el.querySelector('.panel-resize');
    if (!handle) return;

    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.clientX;
      const startY = e.clientY;
      const startW = this.el.offsetWidth;
      const startH = this.el.offsetHeight;
      this.traerAlFrente();

      const onMove = (e) => {
        const newW = Math.max(400, Math.min(window.innerWidth,  startW + e.clientX - startX));
        const newH = Math.max(300, Math.min(window.innerHeight, startH + e.clientY - startY));
        this.el.style.width  = newW + 'px';
        this.el.style.height = newH + 'px';
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup',   onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup',   onUp);
    });
  }

  _initFocus() {
    this.el.addEventListener('mousedown', () => this.traerAlFrente());
  }
}

// ── Registro global ──────────────────────────────────────────────────────────
const _paneles = {};

/** Abre (o trae al frente) el panel con el id dado. */
function abrirPanel(id) {
  if (!_paneles[id]) {
    _paneles[id] = new PanelFlotante(id);
  }
  _paneles[id].abrir();
}
