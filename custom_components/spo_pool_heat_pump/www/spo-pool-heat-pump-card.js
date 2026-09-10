// node_modules/@lit/reactive-element/css-tag.js
var t = globalThis;
var e = t.ShadowRoot && (void 0 === t.ShadyCSS || t.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype;
var s = Symbol();
var o = /* @__PURE__ */ new WeakMap();
var n = class {
  constructor(t3, e4, o5) {
    if (this._$cssResult$ = true, o5 !== s) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t3, this.t = e4;
  }
  get styleSheet() {
    let t3 = this.o;
    const s4 = this.t;
    if (e && void 0 === t3) {
      const e4 = void 0 !== s4 && 1 === s4.length;
      e4 && (t3 = o.get(s4)), void 0 === t3 && ((this.o = t3 = new CSSStyleSheet()).replaceSync(this.cssText), e4 && o.set(s4, t3));
    }
    return t3;
  }
  toString() {
    return this.cssText;
  }
};
var r = (t3) => new n("string" == typeof t3 ? t3 : t3 + "", void 0, s);
var i = (t3, ...e4) => {
  const o5 = 1 === t3.length ? t3[0] : e4.reduce((e5, s4, o6) => e5 + ((t4) => {
    if (true === t4._$cssResult$) return t4.cssText;
    if ("number" == typeof t4) return t4;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + t4 + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(s4) + t3[o6 + 1], t3[0]);
  return new n(o5, t3, s);
};
var S = (s4, o5) => {
  if (e) s4.adoptedStyleSheets = o5.map((t3) => t3 instanceof CSSStyleSheet ? t3 : t3.styleSheet);
  else for (const e4 of o5) {
    const o6 = document.createElement("style"), n4 = t.litNonce;
    void 0 !== n4 && o6.setAttribute("nonce", n4), o6.textContent = e4.cssText, s4.appendChild(o6);
  }
};
var c = e ? (t3) => t3 : (t3) => t3 instanceof CSSStyleSheet ? ((t4) => {
  let e4 = "";
  for (const s4 of t4.cssRules) e4 += s4.cssText;
  return r(e4);
})(t3) : t3;

// node_modules/@lit/reactive-element/reactive-element.js
var { is: i2, defineProperty: e2, getOwnPropertyDescriptor: h, getOwnPropertyNames: r2, getOwnPropertySymbols: o2, getPrototypeOf: n2 } = Object;
var a = globalThis;
var c2 = a.trustedTypes;
var l = c2 ? c2.emptyScript : "";
var p = a.reactiveElementPolyfillSupport;
var d = (t3, s4) => t3;
var u = { toAttribute(t3, s4) {
  switch (s4) {
    case Boolean:
      t3 = t3 ? l : null;
      break;
    case Object:
    case Array:
      t3 = null == t3 ? t3 : JSON.stringify(t3);
  }
  return t3;
}, fromAttribute(t3, s4) {
  let i5 = t3;
  switch (s4) {
    case Boolean:
      i5 = null !== t3;
      break;
    case Number:
      i5 = null === t3 ? null : Number(t3);
      break;
    case Object:
    case Array:
      try {
        i5 = JSON.parse(t3);
      } catch (t4) {
        i5 = null;
      }
  }
  return i5;
} };
var f = (t3, s4) => !i2(t3, s4);
var b = { attribute: true, type: String, converter: u, reflect: false, useDefault: false, hasChanged: f };
Symbol.metadata ??= Symbol("metadata"), a.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
var y = class extends HTMLElement {
  static addInitializer(t3) {
    this._$Ei(), (this.l ??= []).push(t3);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t3, s4 = b) {
    if (s4.state && (s4.attribute = false), this._$Ei(), this.prototype.hasOwnProperty(t3) && ((s4 = Object.create(s4)).wrapped = true), this.elementProperties.set(t3, s4), !s4.noAccessor) {
      const i5 = Symbol(), h3 = this.getPropertyDescriptor(t3, i5, s4);
      void 0 !== h3 && e2(this.prototype, t3, h3);
    }
  }
  static getPropertyDescriptor(t3, s4, i5) {
    const { get: e4, set: r4 } = h(this.prototype, t3) ?? { get() {
      return this[s4];
    }, set(t4) {
      this[s4] = t4;
    } };
    return { get: e4, set(s5) {
      const h3 = e4?.call(this);
      r4?.call(this, s5), this.requestUpdate(t3, h3, i5);
    }, configurable: true, enumerable: true };
  }
  static getPropertyOptions(t3) {
    return this.elementProperties.get(t3) ?? b;
  }
  static _$Ei() {
    if (this.hasOwnProperty(d("elementProperties"))) return;
    const t3 = n2(this);
    t3.finalize(), void 0 !== t3.l && (this.l = [...t3.l]), this.elementProperties = new Map(t3.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(d("finalized"))) return;
    if (this.finalized = true, this._$Ei(), this.hasOwnProperty(d("properties"))) {
      const t4 = this.properties, s4 = [...r2(t4), ...o2(t4)];
      for (const i5 of s4) this.createProperty(i5, t4[i5]);
    }
    const t3 = this[Symbol.metadata];
    if (null !== t3) {
      const s4 = litPropertyMetadata.get(t3);
      if (void 0 !== s4) for (const [t4, i5] of s4) this.elementProperties.set(t4, i5);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [t4, s4] of this.elementProperties) {
      const i5 = this._$Eu(t4, s4);
      void 0 !== i5 && this._$Eh.set(i5, t4);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(s4) {
    const i5 = [];
    if (Array.isArray(s4)) {
      const e4 = new Set(s4.flat(1 / 0).reverse());
      for (const s5 of e4) i5.unshift(c(s5));
    } else void 0 !== s4 && i5.push(c(s4));
    return i5;
  }
  static _$Eu(t3, s4) {
    const i5 = s4.attribute;
    return false === i5 ? void 0 : "string" == typeof i5 ? i5 : "string" == typeof t3 ? t3.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = false, this.hasUpdated = false, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((t3) => this.enableUpdating = t3), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t3) => t3(this));
  }
  addController(t3) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(t3), void 0 !== this.renderRoot && this.isConnected && t3.hostConnected?.();
  }
  removeController(t3) {
    this._$EO?.delete(t3);
  }
  _$E_() {
    const t3 = /* @__PURE__ */ new Map(), s4 = this.constructor.elementProperties;
    for (const i5 of s4.keys()) this.hasOwnProperty(i5) && (t3.set(i5, this[i5]), delete this[i5]);
    t3.size > 0 && (this._$Ep = t3);
  }
  createRenderRoot() {
    const t3 = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return S(t3, this.constructor.elementStyles), t3;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(true), this._$EO?.forEach((t3) => t3.hostConnected?.());
  }
  enableUpdating(t3) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((t3) => t3.hostDisconnected?.());
  }
  attributeChangedCallback(t3, s4, i5) {
    this._$AK(t3, i5);
  }
  _$ET(t3, s4) {
    const i5 = this.constructor.elementProperties.get(t3), e4 = this.constructor._$Eu(t3, i5);
    if (void 0 !== e4 && true === i5.reflect) {
      const h3 = (void 0 !== i5.converter?.toAttribute ? i5.converter : u).toAttribute(s4, i5.type);
      this._$Em = t3, null == h3 ? this.removeAttribute(e4) : this.setAttribute(e4, h3), this._$Em = null;
    }
  }
  _$AK(t3, s4) {
    const i5 = this.constructor, e4 = i5._$Eh.get(t3);
    if (void 0 !== e4 && this._$Em !== e4) {
      const t4 = i5.getPropertyOptions(e4), h3 = "function" == typeof t4.converter ? { fromAttribute: t4.converter } : void 0 !== t4.converter?.fromAttribute ? t4.converter : u;
      this._$Em = e4;
      const r4 = h3.fromAttribute(s4, t4.type);
      this[e4] = r4 ?? this._$Ej?.get(e4) ?? r4, this._$Em = null;
    }
  }
  requestUpdate(t3, s4, i5, e4 = false, h3) {
    if (void 0 !== t3) {
      const r4 = this.constructor;
      if (false === e4 && (h3 = this[t3]), i5 ??= r4.getPropertyOptions(t3), !((i5.hasChanged ?? f)(h3, s4) || i5.useDefault && i5.reflect && h3 === this._$Ej?.get(t3) && !this.hasAttribute(r4._$Eu(t3, i5)))) return;
      this.C(t3, s4, i5);
    }
    false === this.isUpdatePending && (this._$ES = this._$EP());
  }
  C(t3, s4, { useDefault: i5, reflect: e4, wrapped: h3 }, r4) {
    i5 && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(t3) && (this._$Ej.set(t3, r4 ?? s4 ?? this[t3]), true !== h3 || void 0 !== r4) || (this._$AL.has(t3) || (this.hasUpdated || i5 || (s4 = void 0), this._$AL.set(t3, s4)), true === e4 && this._$Em !== t3 && (this._$Eq ??= /* @__PURE__ */ new Set()).add(t3));
  }
  async _$EP() {
    this.isUpdatePending = true;
    try {
      await this._$ES;
    } catch (t4) {
      Promise.reject(t4);
    }
    const t3 = this.scheduleUpdate();
    return null != t3 && await t3, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
        for (const [t5, s5] of this._$Ep) this[t5] = s5;
        this._$Ep = void 0;
      }
      const t4 = this.constructor.elementProperties;
      if (t4.size > 0) for (const [s5, i5] of t4) {
        const { wrapped: t5 } = i5, e4 = this[s5];
        true !== t5 || this._$AL.has(s5) || void 0 === e4 || this.C(s5, void 0, i5, e4);
      }
    }
    let t3 = false;
    const s4 = this._$AL;
    try {
      t3 = this.shouldUpdate(s4), t3 ? (this.willUpdate(s4), this._$EO?.forEach((t4) => t4.hostUpdate?.()), this.update(s4)) : this._$EM();
    } catch (s5) {
      throw t3 = false, this._$EM(), s5;
    }
    t3 && this._$AE(s4);
  }
  willUpdate(t3) {
  }
  _$AE(t3) {
    this._$EO?.forEach((t4) => t4.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = true, this.firstUpdated(t3)), this.updated(t3);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = false;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(t3) {
    return true;
  }
  update(t3) {
    this._$Eq &&= this._$Eq.forEach((t4) => this._$ET(t4, this[t4])), this._$EM();
  }
  updated(t3) {
  }
  firstUpdated(t3) {
  }
};
y.elementStyles = [], y.shadowRootOptions = { mode: "open" }, y[d("elementProperties")] = /* @__PURE__ */ new Map(), y[d("finalized")] = /* @__PURE__ */ new Map(), p?.({ ReactiveElement: y }), (a.reactiveElementVersions ??= []).push("2.1.2");

// node_modules/lit-html/lit-html.js
var t2 = globalThis;
var i3 = (t3) => t3;
var s2 = t2.trustedTypes;
var e3 = s2 ? s2.createPolicy("lit-html", { createHTML: (t3) => t3 }) : void 0;
var h2 = "$lit$";
var o3 = `lit$${Math.random().toFixed(9).slice(2)}$`;
var n3 = "?" + o3;
var r3 = `<${n3}>`;
var l2 = document;
var c3 = () => l2.createComment("");
var a2 = (t3) => null === t3 || "object" != typeof t3 && "function" != typeof t3;
var u2 = Array.isArray;
var d2 = (t3) => u2(t3) || "function" == typeof t3?.[Symbol.iterator];
var f2 = "[ 	\n\f\r]";
var v = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;
var _ = /-->/g;
var m = />/g;
var p2 = RegExp(`>|${f2}(?:([^\\s"'>=/]+)(${f2}*=${f2}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g");
var g = /'/g;
var $ = /"/g;
var y2 = /^(?:script|style|textarea|title)$/i;
var x = (t3) => (i5, ...s4) => ({ _$litType$: t3, strings: i5, values: s4 });
var b2 = x(1);
var w = x(2);
var T = x(3);
var E = Symbol.for("lit-noChange");
var A = Symbol.for("lit-nothing");
var C = /* @__PURE__ */ new WeakMap();
var P = l2.createTreeWalker(l2, 129);
function V(t3, i5) {
  if (!u2(t3) || !t3.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return void 0 !== e3 ? e3.createHTML(i5) : i5;
}
var N = (t3, i5) => {
  const s4 = t3.length - 1, e4 = [];
  let n4, l3 = 2 === i5 ? "<svg>" : 3 === i5 ? "<math>" : "", c4 = v;
  for (let i6 = 0; i6 < s4; i6++) {
    const s5 = t3[i6];
    let a3, u3, d3 = -1, f3 = 0;
    for (; f3 < s5.length && (c4.lastIndex = f3, u3 = c4.exec(s5), null !== u3); ) f3 = c4.lastIndex, c4 === v ? "!--" === u3[1] ? c4 = _ : void 0 !== u3[1] ? c4 = m : void 0 !== u3[2] ? (y2.test(u3[2]) && (n4 = RegExp("</" + u3[2], "g")), c4 = p2) : void 0 !== u3[3] && (c4 = p2) : c4 === p2 ? ">" === u3[0] ? (c4 = n4 ?? v, d3 = -1) : void 0 === u3[1] ? d3 = -2 : (d3 = c4.lastIndex - u3[2].length, a3 = u3[1], c4 = void 0 === u3[3] ? p2 : '"' === u3[3] ? $ : g) : c4 === $ || c4 === g ? c4 = p2 : c4 === _ || c4 === m ? c4 = v : (c4 = p2, n4 = void 0);
    const x2 = c4 === p2 && t3[i6 + 1].startsWith("/>") ? " " : "";
    l3 += c4 === v ? s5 + r3 : d3 >= 0 ? (e4.push(a3), s5.slice(0, d3) + h2 + s5.slice(d3) + o3 + x2) : s5 + o3 + (-2 === d3 ? i6 : x2);
  }
  return [V(t3, l3 + (t3[s4] || "<?>") + (2 === i5 ? "</svg>" : 3 === i5 ? "</math>" : "")), e4];
};
var S2 = class _S {
  constructor({ strings: t3, _$litType$: i5 }, e4) {
    let r4;
    this.parts = [];
    let l3 = 0, a3 = 0;
    const u3 = t3.length - 1, d3 = this.parts, [f3, v2] = N(t3, i5);
    if (this.el = _S.createElement(f3, e4), P.currentNode = this.el.content, 2 === i5 || 3 === i5) {
      const t4 = this.el.content.firstChild;
      t4.replaceWith(...t4.childNodes);
    }
    for (; null !== (r4 = P.nextNode()) && d3.length < u3; ) {
      if (1 === r4.nodeType) {
        if (r4.hasAttributes()) for (const t4 of r4.getAttributeNames()) if (t4.endsWith(h2)) {
          const i6 = v2[a3++], s4 = r4.getAttribute(t4).split(o3), e5 = /([.?@])?(.*)/.exec(i6);
          d3.push({ type: 1, index: l3, name: e5[2], strings: s4, ctor: "." === e5[1] ? I : "?" === e5[1] ? L : "@" === e5[1] ? z : H }), r4.removeAttribute(t4);
        } else t4.startsWith(o3) && (d3.push({ type: 6, index: l3 }), r4.removeAttribute(t4));
        if (y2.test(r4.tagName)) {
          const t4 = r4.textContent.split(o3), i6 = t4.length - 1;
          if (i6 > 0) {
            r4.textContent = s2 ? s2.emptyScript : "";
            for (let s4 = 0; s4 < i6; s4++) r4.append(t4[s4], c3()), P.nextNode(), d3.push({ type: 2, index: ++l3 });
            r4.append(t4[i6], c3());
          }
        }
      } else if (8 === r4.nodeType) if (r4.data === n3) d3.push({ type: 2, index: l3 });
      else {
        let t4 = -1;
        for (; -1 !== (t4 = r4.data.indexOf(o3, t4 + 1)); ) d3.push({ type: 7, index: l3 }), t4 += o3.length - 1;
      }
      l3++;
    }
  }
  static createElement(t3, i5) {
    const s4 = l2.createElement("template");
    return s4.innerHTML = t3, s4;
  }
};
function M(t3, i5, s4 = t3, e4) {
  if (i5 === E) return i5;
  let h3 = void 0 !== e4 ? s4._$Co?.[e4] : s4._$Cl;
  const o5 = a2(i5) ? void 0 : i5._$litDirective$;
  return h3?.constructor !== o5 && (h3?._$AO?.(false), void 0 === o5 ? h3 = void 0 : (h3 = new o5(t3), h3._$AT(t3, s4, e4)), void 0 !== e4 ? (s4._$Co ??= [])[e4] = h3 : s4._$Cl = h3), void 0 !== h3 && (i5 = M(t3, h3._$AS(t3, i5.values), h3, e4)), i5;
}
var R = class {
  constructor(t3, i5) {
    this._$AV = [], this._$AN = void 0, this._$AD = t3, this._$AM = i5;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t3) {
    const { el: { content: i5 }, parts: s4 } = this._$AD, e4 = (t3?.creationScope ?? l2).importNode(i5, true);
    P.currentNode = e4;
    let h3 = P.nextNode(), o5 = 0, n4 = 0, r4 = s4[0];
    for (; void 0 !== r4; ) {
      if (o5 === r4.index) {
        let i6;
        2 === r4.type ? i6 = new k(h3, h3.nextSibling, this, t3) : 1 === r4.type ? i6 = new r4.ctor(h3, r4.name, r4.strings, this, t3) : 6 === r4.type && (i6 = new Z(h3, this, t3)), this._$AV.push(i6), r4 = s4[++n4];
      }
      o5 !== r4?.index && (h3 = P.nextNode(), o5++);
    }
    return P.currentNode = l2, e4;
  }
  p(t3) {
    let i5 = 0;
    for (const s4 of this._$AV) void 0 !== s4 && (void 0 !== s4.strings ? (s4._$AI(t3, s4, i5), i5 += s4.strings.length - 2) : s4._$AI(t3[i5])), i5++;
  }
};
var k = class _k {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t3, i5, s4, e4) {
    this.type = 2, this._$AH = A, this._$AN = void 0, this._$AA = t3, this._$AB = i5, this._$AM = s4, this.options = e4, this._$Cv = e4?.isConnected ?? true;
  }
  get parentNode() {
    let t3 = this._$AA.parentNode;
    const i5 = this._$AM;
    return void 0 !== i5 && 11 === t3?.nodeType && (t3 = i5.parentNode), t3;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t3, i5 = this) {
    t3 = M(this, t3, i5), a2(t3) ? t3 === A || null == t3 || "" === t3 ? (this._$AH !== A && this._$AR(), this._$AH = A) : t3 !== this._$AH && t3 !== E && this._(t3) : void 0 !== t3._$litType$ ? this.$(t3) : void 0 !== t3.nodeType ? this.T(t3) : d2(t3) ? this.k(t3) : this._(t3);
  }
  O(t3) {
    return this._$AA.parentNode.insertBefore(t3, this._$AB);
  }
  T(t3) {
    this._$AH !== t3 && (this._$AR(), this._$AH = this.O(t3));
  }
  _(t3) {
    this._$AH !== A && a2(this._$AH) ? this._$AA.nextSibling.data = t3 : this.T(l2.createTextNode(t3)), this._$AH = t3;
  }
  $(t3) {
    const { values: i5, _$litType$: s4 } = t3, e4 = "number" == typeof s4 ? this._$AC(t3) : (void 0 === s4.el && (s4.el = S2.createElement(V(s4.h, s4.h[0]), this.options)), s4);
    if (this._$AH?._$AD === e4) this._$AH.p(i5);
    else {
      const t4 = new R(e4, this), s5 = t4.u(this.options);
      t4.p(i5), this.T(s5), this._$AH = t4;
    }
  }
  _$AC(t3) {
    let i5 = C.get(t3.strings);
    return void 0 === i5 && C.set(t3.strings, i5 = new S2(t3)), i5;
  }
  k(t3) {
    u2(this._$AH) || (this._$AH = [], this._$AR());
    const i5 = this._$AH;
    let s4, e4 = 0;
    for (const h3 of t3) e4 === i5.length ? i5.push(s4 = new _k(this.O(c3()), this.O(c3()), this, this.options)) : s4 = i5[e4], s4._$AI(h3), e4++;
    e4 < i5.length && (this._$AR(s4 && s4._$AB.nextSibling, e4), i5.length = e4);
  }
  _$AR(t3 = this._$AA.nextSibling, s4) {
    for (this._$AP?.(false, true, s4); t3 !== this._$AB; ) {
      const s5 = i3(t3).nextSibling;
      i3(t3).remove(), t3 = s5;
    }
  }
  setConnected(t3) {
    void 0 === this._$AM && (this._$Cv = t3, this._$AP?.(t3));
  }
};
var H = class {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t3, i5, s4, e4, h3) {
    this.type = 1, this._$AH = A, this._$AN = void 0, this.element = t3, this.name = i5, this._$AM = e4, this.options = h3, s4.length > 2 || "" !== s4[0] || "" !== s4[1] ? (this._$AH = Array(s4.length - 1).fill(new String()), this.strings = s4) : this._$AH = A;
  }
  _$AI(t3, i5 = this, s4, e4) {
    const h3 = this.strings;
    let o5 = false;
    if (void 0 === h3) t3 = M(this, t3, i5, 0), o5 = !a2(t3) || t3 !== this._$AH && t3 !== E, o5 && (this._$AH = t3);
    else {
      const e5 = t3;
      let n4, r4;
      for (t3 = h3[0], n4 = 0; n4 < h3.length - 1; n4++) r4 = M(this, e5[s4 + n4], i5, n4), r4 === E && (r4 = this._$AH[n4]), o5 ||= !a2(r4) || r4 !== this._$AH[n4], r4 === A ? t3 = A : t3 !== A && (t3 += (r4 ?? "") + h3[n4 + 1]), this._$AH[n4] = r4;
    }
    o5 && !e4 && this.j(t3);
  }
  j(t3) {
    t3 === A ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t3 ?? "");
  }
};
var I = class extends H {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t3) {
    this.element[this.name] = t3 === A ? void 0 : t3;
  }
};
var L = class extends H {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t3) {
    this.element.toggleAttribute(this.name, !!t3 && t3 !== A);
  }
};
var z = class extends H {
  constructor(t3, i5, s4, e4, h3) {
    super(t3, i5, s4, e4, h3), this.type = 5;
  }
  _$AI(t3, i5 = this) {
    if ((t3 = M(this, t3, i5, 0) ?? A) === E) return;
    const s4 = this._$AH, e4 = t3 === A && s4 !== A || t3.capture !== s4.capture || t3.once !== s4.once || t3.passive !== s4.passive, h3 = t3 !== A && (s4 === A || e4);
    e4 && this.element.removeEventListener(this.name, this, s4), h3 && this.element.addEventListener(this.name, this, t3), this._$AH = t3;
  }
  handleEvent(t3) {
    "function" == typeof this._$AH ? this._$AH.call(this.options?.host ?? this.element, t3) : this._$AH.handleEvent(t3);
  }
};
var Z = class {
  constructor(t3, i5, s4) {
    this.element = t3, this.type = 6, this._$AN = void 0, this._$AM = i5, this.options = s4;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t3) {
    M(this, t3);
  }
};
var B = t2.litHtmlPolyfillSupport;
B?.(S2, k), (t2.litHtmlVersions ??= []).push("3.3.3");
var D = (t3, i5, s4) => {
  const e4 = s4?.renderBefore ?? i5;
  let h3 = e4._$litPart$;
  if (void 0 === h3) {
    const t4 = s4?.renderBefore ?? null;
    e4._$litPart$ = h3 = new k(i5.insertBefore(c3(), t4), t4, void 0, s4 ?? {});
  }
  return h3._$AI(t3), h3;
};

// node_modules/lit-element/lit-element.js
var s3 = globalThis;
var i4 = class extends y {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const t3 = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= t3.firstChild, t3;
  }
  update(t3) {
    const r4 = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t3), this._$Do = D(r4, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(true);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(false);
  }
  render() {
    return E;
  }
};
i4._$litElement$ = true, i4["finalized"] = true, s3.litElementHydrateSupport?.({ LitElement: i4 });
var o4 = s3.litElementPolyfillSupport;
o4?.({ LitElement: i4 });
(s3.litElementVersions ??= []).push("4.2.2");

// host.css
var host_default = ':host { display: block; container-type: inline-size; container-name: php; }\nha-card.card { overflow: hidden; position: relative; }\nha-card.card button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; }\n.stale { position: absolute; inset: 0; display: grid; place-items: center; z-index: 5; pointer-events: none; }\n.stale span { background: var(--card-background-color); border: 1px solid var(--ha-card-border-color); padding: 8px 14px; border-radius: 999px; font-size: 13px; color: var(--secondary-text-color); display: inline-flex; gap: 8px; align-items: center; }\n.stale i { width: 8px; height: 8px; border-radius: 50%; background: #e53935; display: inline-block; }\n.card[data-available="false"] .w3 { filter: grayscale(1); opacity: 0.45; }\n\nha-dialog {\n  --mdc-dialog-min-width: min(720px, 96vw);\n  --mdc-dialog-max-width: 96vw;\n  --mdc-dialog-max-height: 92vh;\n}\nha-card.params-card { overflow: auto; max-height: calc(100vh - 120px); padding: 12px 16px 16px; }\n.params-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }\n.params-refresh {\n  font: inherit;\n  font-size: 13px;\n  color: var(--primary-color);\n  background: none;\n  border: 0;\n  padding: 4px 0;\n  cursor: pointer;\n}\n.params-browser { overflow: auto; max-height: 70vh; padding-right: 4px; }\n.params-filter, .params-groups {\n  width: 100%;\n  margin: 6px 0;\n  box-sizing: border-box;\n  border: 1px solid var(--divider-color);\n  border-radius: 8px;\n  background: transparent;\n  color: inherit;\n  font: inherit;\n  padding: 6px 10px;\n}\n.params-count { font-size: 12px; color: var(--secondary-text-color); padding: 2px 0 6px; }\n.params-row {\n  display: grid;\n  grid-template-columns: 1fr auto;\n  gap: 10px;\n  align-items: center;\n  padding: 4px 0;\n  border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent);\n}\n.params-label { font-size: 13px; min-width: 0; }\n.params-val { font-variant-numeric: tabular-nums; color: var(--secondary-text-color); font-size: 13px; }\n.params-edit { display: inline-flex; align-items: center; gap: 4px; }\n.params-edit small { color: var(--secondary-text-color); }\n.params-input {\n  width: 88px;\n  border: 1px solid var(--divider-color);\n  border-radius: 6px;\n  background: transparent;\n  color: inherit;\n  font: inherit;\n  font-variant-numeric: tabular-nums;\n  padding: 3px 6px;\n  text-align: right;\n}\n.params-row.service_menu .params-input { border-color: color-mix(in srgb, #e53935 45%, var(--divider-color)); }\n.params-note, .params-error { font-size: 12px; color: var(--secondary-text-color); padding: 4px 0; }\n.params-error { color: #e53935; }\n.settings-tabs { display: flex; gap: 8px; margin: 4px 0 10px; }\n.settings-tabs button {\n  font: inherit;\n  font-size: 13px;\n  color: var(--secondary-text-color);\n  background: color-mix(in srgb, var(--primary-text-color) 7%, transparent);\n  border: 1px solid var(--divider-color);\n  border-radius: 999px;\n  padding: 4px 12px;\n  cursor: pointer;\n}\n.settings-tabs button.on { color: var(--primary-text-color); border-color: var(--primary-color); }\n.dump-panel { display: grid; gap: 8px; }\n.dump-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }\n.dump-title { font-size: 13px; color: var(--secondary-text-color); }\n.dump-help-btn {\n  width: 28px;\n  height: 28px;\n  border-radius: 50%;\n  border: 1px solid var(--divider-color);\n  background: color-mix(in srgb, var(--primary-text-color) 7%, transparent);\n  color: inherit;\n  font: inherit;\n  font-size: 15px;\n  font-weight: 600;\n  line-height: 1;\n  cursor: pointer;\n  padding: 0;\n}\n.dump-help-btn.on { color: var(--primary-text-color); border-color: var(--primary-color); }\n.dump-help {\n  font-size: 13px;\n  line-height: 1.45;\n  color: var(--primary-text-color);\n  background: color-mix(in srgb, var(--primary-text-color) 5%, transparent);\n  border: 1px solid var(--divider-color);\n  border-radius: 10px;\n  padding: 10px 12px;\n}\n.dump-help p { margin: 0 0 8px; }\n.dump-help p:last-child { margin-bottom: 0; }\n.dump-help ul { margin: 0 0 8px; padding-left: 1.2em; }\n.dump-help li { margin: 0 0 4px; }\n.dump-help code { font-family: ui-monospace, Consolas, monospace; font-size: 0.92em; }\n.dump-field { display: grid; gap: 4px; font-size: 13px; }\n.dump-minutes { width: 72px; text-align: left; }\n.dump-check { display: flex; align-items: center; gap: 8px; font-size: 13px; }\n.dump-btn {\n  justify-self: start;\n  font: inherit;\n  font-size: 13px;\n  color: var(--primary-text-color);\n  background: color-mix(in srgb, var(--primary-color) 16%, transparent);\n  border: 1px solid var(--primary-color);\n  border-radius: 8px;\n  padding: 6px 12px;\n  cursor: pointer;\n}\n.dump-file {\n  display: grid;\n  gap: 6px;\n  padding: 8px 0;\n  border-top: 1px solid color-mix(in srgb, var(--divider-color) 70%, transparent);\n}\n.dump-actions { display: flex; flex-wrap: wrap; gap: 10px; }\n.dump-link {\n  font: inherit;\n  font-size: 12px;\n  color: var(--primary-color);\n  background: none;\n  border: 0;\n  padding: 0;\n  cursor: pointer;\n}\n';

// wave3.css
var wave3_default = '/* Canonical pool-heatpump card stylesheet.\n   Mock host: .card.w3 inside tokens.css.\n   Lit host: same rules plus card-src/host.css; esbuild concatenates both. */\n\n/* tokens \u2014 --cold --warm; HA theme vars come from the host */\n.w3 {\n  --cold: #38b6ff;\n  --warm: #ff8a3d;\n  padding: 22px 24px 18px;\n  display: grid;\n  gap: 16px;\n}\n.w3 > * { min-width: 0; }\n\n/* chrome \u2014 grid: top, hero, target, facts, modes, .ib, .seg */\n.w3 .eyebrow {\n  font-size: 12.5px;\n  letter-spacing: 0;\n  text-transform: none;\n  color: var(--secondary-text-color);\n  font-weight: 400;\n}\n.w3 .top { display: flex; justify-content: space-between; align-items: flex-start; }\n.w3 .top .eyebrow:first-child { font-size: 15px; font-weight: 500; color: var(--primary-text-color); }\n.w3 .top .status-block { display: flex; flex-direction: column; align-items: flex-end; gap: 2px; min-width: 0; }\n.w3 .top .status { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; font-size: 12.5px; }\n.w3 .top .status i { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }\n.w3 .top .fault-why {\n  font-size: 12px;\n  line-height: 1.25;\n  color: #e53935;\n  max-width: min(220px, 52cqi);\n  text-align: right;\n}\n.w3 .hero { display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 16px; }\n.w3 .num { font-weight: 300; letter-spacing: -.02em; line-height: .9; font-variant-numeric: tabular-nums; }\n.w3 .big .num { font-size: 64px; }\n.w3 .big .unit {\n  font-size: 26px;\n  font-weight: 200;\n  vertical-align: top;\n  position: relative;\n  top: 6px;\n  margin-left: 2px;\n  color: var(--secondary-text-color);\n}\n.w3 .target {\n  display: grid;\n  grid-template-columns: 32px auto 32px;\n  grid-template-rows: auto auto;\n  column-gap: 10px;\n  align-items: center;\n  justify-items: center;\n}\n.w3 .target .eyebrow { grid-column: 2; grid-row: 1; margin: 0; text-align: center; }\n.w3 .target .ib:first-of-type { grid-column: 1; grid-row: 2; }\n.w3 .target .val { grid-column: 2; grid-row: 2; }\n.w3 .target .ib:last-of-type { grid-column: 3; grid-row: 2; }\n.w3 .target .num { font-size: 32px; }\n.w3 .target .unit {\n  font-size: 16px;\n  font-weight: 200;\n  color: var(--secondary-text-color);\n  vertical-align: top;\n  position: relative;\n  top: 3px;\n}\n.w3 .ib {\n  width: 34px;\n  height: 34px;\n  border-radius: 50%;\n  border: 1px solid var(--divider-color);\n  display: grid;\n  place-items: center;\n  color: var(--secondary-text-color);\n  transition: border-color .2s, background-color .2s;\n}\n.w3 .ib svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }\n.w3 .ib:hover { border-color: color-mix(in srgb, var(--primary-text-color) 30%, transparent); }\n.w3 .ib.pw.on { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 45%, transparent); background: color-mix(in srgb, var(--accent) 8%, transparent); }\n.w3 .ib.quiet.on { color: #2bb5a0; border-color: color-mix(in srgb, #2bb5a0 45%, transparent); background: color-mix(in srgb, #2bb5a0 8%, transparent); }\n.w3 .target .ib { width: 32px; height: 32px; }\n.w3 .seg { display: inline-flex; padding: 3px; border-radius: 999px; border: 1px solid var(--divider-color); }\n.w3 .seg button {\n  padding: 6px 14px;\n  border-radius: 999px;\n  font-size: 13px;\n  font-weight: 500;\n  color: var(--secondary-text-color);\n  line-height: 1;\n  transition: background-color .2s, color .2s;\n}\n.w3 .seg button.on { color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }\n.card[data-action="off"] .seg button.on { color: var(--secondary-text-color); background: color-mix(in srgb, var(--primary-text-color) 7%, transparent); }\n.w3 .modes { display: flex; gap: 8px; align-items: center; border-top: 1px solid var(--divider-color); padding-top: 14px; }\n.w3 .modes .sp { flex: 1; }\n.w3 .facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; }\n.w3 .fact { padding: 0 14px; border-left: 1px solid var(--divider-color); }\n.w3 .fact:first-child { padding-left: 0; border-left: 0; }\n.w3 .fact .v { font-size: 20px; font-weight: 400; letter-spacing: -.03em; line-height: 1.1; }\n.w3 .fact .v small { font-size: 11px; color: var(--secondary-text-color); margin-left: 3px; font-weight: 400; letter-spacing: 0; }\n.w3 .fact .eyebrow { margin-top: 2px; display: block; font-size: 12px; }\n\n/* drawing \u2014 shared SVG primitives */\n.w3 svg.dwg { width: 100%; height: auto; display: block; overflow: visible; }\n.dwg .ln { fill: none; stroke: color-mix(in srgb, var(--primary-text-color) 38%, transparent); stroke-width: 1; stroke-linejoin: round; stroke-linecap: round; }\n.dwg .thin { fill: none; stroke: color-mix(in srgb, var(--primary-text-color) 30%, transparent); stroke-width: .9; stroke-linecap: round; }\n.dwg .water { fill: color-mix(in srgb, var(--cold) 18%, transparent); }\n.card[data-action="off"] .dwg .water { fill: color-mix(in srgb, var(--primary-text-color) 6%, transparent); }\n.card[data-action="cooling"] .dwg .plume { filter: saturate(1.6) brightness(1.15); }\n.dwg text { font-family: var(--font); fill: var(--primary-text-color); }\n.dwg .k { letter-spacing: 0; text-transform: capitalize; fill: var(--secondary-text-color); font-weight: 400; font-size: 11px; }\n.dwg .v { font-weight: 400; letter-spacing: -.02em; font-size: 16px; }\n.dwg .v.warm { fill: var(--warm); }\n.dwg .v.cool { fill: var(--cold); }\n.dwg .halo { stroke: var(--card-background-color); stroke-width: 4px; paint-order: stroke fill; stroke-linejoin: round; }\n.dwg .tube { fill: none; stroke-width: 9; stroke-linecap: round; stroke-linejoin: round; opacity: .22; }\n.dwg .core { fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }\n.dwg .tube.in, .dwg .core.in { stroke: var(--inC); }\n.dwg .tube.out, .dwg .core.out { stroke: var(--outC); }\n.dwg .dots { fill: none; stroke: #fff; stroke-width: 3.2; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 0 18; opacity: 0; }\n.card[data-pump="true"] .dwg .dots { opacity: .85; animation: dots 2.4s linear infinite; }\n.card[data-silent="true"] .dwg .dots { animation-duration: 4s; }\n.dwg .plume { opacity: 0; }\n.card[data-pump="true"] .dwg .plume { opacity: 1; animation: plume 3.2s ease-in-out infinite alternate; }\n.dwg .led { fill: var(--accent); filter: drop-shadow(0 0 4px var(--accent)); }\n.card[data-action="off"] .dwg .led { filter: none; opacity: .35; }\n.dwg .surface { stroke: color-mix(in srgb, var(--primary-text-color) 42%, transparent); animation: surf 6s ease-in-out infinite alternate; }\n.dwg .petal { fill: color-mix(in srgb, var(--primary-text-color) 42%, transparent); }\n.dwg .hub { fill: var(--card-background-color); stroke: color-mix(in srgb, var(--primary-text-color) 55%, transparent); stroke-width: 1.2; }\n.dwg .unitfill { fill: color-mix(in srgb, var(--primary-text-color) 3.5%, transparent); }\n.card[data-action="heating"] .dwg .unitfill { fill: color-mix(in srgb, var(--warm) 7%, transparent); }\n.card[data-action="cooling"] .dwg .unitfill { fill: color-mix(in srgb, var(--cold) 8%, transparent); }\n.dwg .fanwrap { transform-box: view-box; transform-origin: 0 0; }\n.card[data-action="heating"] .dwg .fanwrap,\n.card[data-action="cooling"] .dwg .fanwrap { animation: spin 2.6s linear infinite; }\n.card[data-silent="true"] .dwg .fanwrap { animation-duration: 5.5s; }\n.dwg .rad-glow { fill: none; stroke-width: 6; stroke-linecap: round; opacity: .22; }\n.dwg .rad-tube { fill: none; stroke-width: 2.3; stroke-linecap: round; }\n.dwg .manifold { fill: none; stroke-width: 4.2; stroke-linecap: round; }\n.dwg .manifold.in { stroke: var(--inC); }\n.dwg .manifold.out { stroke: var(--outC); }\n.dwg .fin { fill: none; stroke: color-mix(in srgb, var(--primary-text-color) 16%, transparent); stroke-width: .7; }\n.dwg .dots.rise { stroke-width: 2.4; }\n.dwg .port { fill: var(--card-background-color); stroke-width: 1.6; }\n.dwg .port.in { stroke: var(--inC); }\n.dwg .port.out { stroke: var(--outC); }\n.dwg .g-disk { fill: color-mix(in srgb, var(--primary-text-color) 4%, transparent); }\n.dwg .g-ring { fill: none; stroke: color-mix(in srgb, var(--primary-text-color) 34%, transparent); stroke-width: 1; }\n.dwg .wall { fill: none; stroke: color-mix(in srgb, var(--primary-text-color) 28%, transparent); stroke-width: 1; stroke-linecap: round; stroke-linejoin: round; }\n\n/* circuit \u2014 19c open basin. Geometry lives in the SVG; no extra paint. */\n\n/* section \u2014 17b cutaway */\n.section .dwg .soil { fill: color-mix(in srgb, var(--primary-text-color) 3.5%, transparent); }\n.section .dwg .grade { opacity: .7; }\n.dwg .nozzle { fill: var(--outC); opacity: .85; }\n.dwg .deck-slab { fill: color-mix(in srgb, var(--primary-text-color) 8%, transparent); }\n.dwg .foot { fill: none; stroke: color-mix(in srgb, var(--primary-text-color) 32%, transparent); stroke-width: 1.2; stroke-linecap: square; }\n\n/* motion */\n@keyframes dots { to { stroke-dashoffset: -36; } }\n@keyframes spin { to { transform: rotate(360deg); } }\n@keyframes plume { from { transform: scale(.85); } to { transform: scale(1.1); } }\n@keyframes surf { from { transform: translateX(-4px); } to { transform: translateX(4px); } }\n.card[data-flow="false"] .dwg .dots,\n.card[data-flow="false"] .dwg .fanwrap,\n.card[data-flow="false"] .dwg .plume,\n.card[data-flow="false"] .dwg .surface { animation: none; }\n.card[data-flow="false"] .dwg .dots { opacity: 0; }\n.card[data-flow="false"] .dwg .plume { opacity: 0; transform: none; }\n.card[data-flow="false"] .dwg .fanwrap { transform: none; }\n@media (prefers-reduced-motion: reduce) {\n  .dwg .dots, .dwg .fanwrap, .dwg .plume, .dwg .surface { animation: none; }\n  .dwg .dots { opacity: 0; }\n  .dwg .plume { opacity: 0; transform: none; }\n}\n\n/* narrow \u2014 container query on the card; keep hero side-by-side */\n@container php (max-width: 379px) {\n  .w3 { padding: 18px 18px 16px; gap: 14px; }\n  .w3 .hero { gap: 8px; }\n  .w3 .big .num { font-size: 48px; }\n  .w3 .big .unit { font-size: 19px; top: 4px; }\n  .w3 .target .num { font-size: 24px; }\n  .w3 .target .unit { font-size: 13px; top: 2px; }\n  .w3 .target { column-gap: 6px; grid-template-columns: 28px auto 28px; }\n  .w3 .target .ib { width: 28px; height: 28px; }\n  .w3 .target .ib svg { width: 14px; height: 14px; }\n  .w3 .seg button { padding: 6px 11px; font-size: 12.5px; }\n  .w3 .modes { gap: 6px; }\n  .w3 .facts { grid-template-columns: repeat(2, 1fr); row-gap: 12px; }\n  .w3 .fact:nth-child(odd) { border-left: 0; padding-left: 0; }\n}\n';

// drawing.ts
var COLD = "#38b6ff";
var WARM = "#ff8a3d";
var NEUT = "#7fb2c9";
var OFFC = "color-mix(in srgb, var(--primary-text-color) 22%, transparent)";
function flow(s4) {
  const on = s4.available && s4.power && s4.pump;
  if (!on) return { inC: OFFC, outC: OFFC };
  const d3 = (s4.outlet ?? 0) - (s4.inlet ?? 0);
  if (Math.abs(d3) < 0.15) return { inC: NEUT, outC: NEUT };
  return d3 > 0 ? { inC: COLD, outC: WARM } : { inC: WARM, outC: COLD };
}
function accent(s4) {
  if (s4.fault) return "#e53935";
  if (!s4.available || !s4.power) return "var(--state-climate-off-color)";
  if (s4.action === "heating" || s4.action === "warmup") return "var(--state-climate-heat-color)";
  if (s4.action === "cooling" || s4.action === "precool") return "var(--state-climate-cool-color)";
  return "var(--state-climate-idle-color)";
}
var f1 = (x2) => x2 == null ? "\u2013" : (Math.round(x2 * 10) / 10).toFixed(1);
var wave = (x0, x1, y3, amp = 3, seg = 12) => {
  let d3 = `M${x0} ${y3}`;
  for (let x2 = x0; x2 < x1; x2 += seg) d3 += ` q${seg / 2} ${-amp} ${seg} 0`;
  return d3;
};
var pipe = (d3, cls) => w`
  <path class="tube ${cls}" d=${d3}/>
  <path class="core ${cls}" d=${d3}/>
  <path class="dots" d=${d3}/>
`;
var vent = (cx, cy, r4) => w`<g class="vent">
  <circle class="g-disk" cx=${cx} cy=${cy} r=${r4 + 1.2}/>
  <circle class="g-ring" cx=${cx} cy=${cy} r=${r4}/>
  <g transform="translate(${cx} ${cy})"><g class="fanwrap">${[0, 120, 240].map((a3) => w`<path class="petal" transform="rotate(${a3})" d=${`M0 0 C ${r4 * 0.28} ${-r4 * 0.42}, ${r4 * 0.7} ${-r4 * 0.55}, ${r4 * 0.76} ${-r4 * 0.1} C ${r4 * 0.55} ${r4 * 0.08}, ${r4 * 0.28} ${r4 * 0.18}, 0 0 Z`}/>`)}</g></g>
  <circle class="hub" cx=${cx} cy=${cy} r=${r4 * 0.15}/>
</g>`;
var radiator = (id, x2, yIn, yOut, w2, n4 = 6) => {
  const top = yOut, bot = yIn, left = x2, right = x2 + w2;
  const inset = 7, span = right - left - inset * 2;
  const tubes = Array.from({ length: n4 }, (_2, i5) => {
    const tx = (left + inset + (n4 === 1 ? 0 : span * i5 / (n4 - 1))).toFixed(1);
    return w`<path class="rad-glow" d=${`M${tx} ${bot} V${top}`} stroke=${`url(#${id})`}/><path class="rad-tube" d=${`M${tx} ${bot} V${top}`} stroke=${`url(#${id})`}/>`;
  });
  const fn = n4 * 2;
  const fins = Array.from({ length: fn }, (_2, i5) => {
    const fx = (left + 6 + (right - left - 12) * i5 / (fn - 1)).toFixed(1);
    return w`<path class="fin" d=${`M${fx} ${bot - 1} V${top + 1}`}/>`;
  });
  const mid = (left + inset + span * 0.5).toFixed(1);
  return w`
    <defs><linearGradient id=${id} gradientUnits="userSpaceOnUse" x1="0" y1=${bot} x2="0" y2=${top}>
      <stop offset="0" stop-color="var(--inC)"/><stop offset=".2" stop-color="var(--inC)"/>
      <stop offset=".65" stop-color="var(--outC)"/><stop offset="1" stop-color="var(--outC)"/>
    </linearGradient></defs>
    <g class="rad"><g class="fins">${fins}</g>${tubes}
      <path class="manifold in" d=${`M${left} ${bot} H${right}`}/><path class="manifold out" d=${`M${left} ${top} H${right}`}/>
      <path class="dots rise" d=${`M${mid} ${bot} V${top}`}/></g>`;
};
var port = (x2, y3, cls) => w`<circle class="port ${cls}" cx=${x2} cy=${y3} r="3.2"/>`;
var plume = (id, cx, cy, rx, ry, clipD) => w`
  <defs>
    <radialGradient id=${id}>
      <stop offset="0" stop-color="var(--outC)" stop-opacity=".55"/>
      <stop offset="1" stop-color="var(--outC)" stop-opacity="0"/>
    </radialGradient>
    <clipPath id="${id}c">${w`<path d=${clipD}/>`}</clipPath>
  </defs>
  <g clip-path=${`url(#${id}c)`}><ellipse class="plume" cx=${cx} cy=${cy} rx=${rx} ry=${ry} fill=${`url(#${id})`} style=${`transform-origin:${cx}px ${cy}px`}/></g>
`;
function tone(s4, which) {
  const f3 = flow(s4);
  if (f3.inC === OFFC || f3.inC === NEUT) return "";
  const heating = f3.outC === WARM;
  return which === "in" === heating ? "cool" : "warm";
}
function portLbl(s4, which, x2, yCap, yVal) {
  const cap = which === "in" ? "In" : "Out";
  const val = `${f1(which === "in" ? s4.inlet : s4.outlet)}\xB0`;
  return w`<text class="k halo" x=${x2} y=${yCap} text-anchor="end">${cap}</text><text class="v halo ${tone(s4, which)}" x=${x2} y=${yVal} text-anchor="end">${val}</text>`;
}
function airMark(s4, x2, y3) {
  if (!s4.caps.ambient) return A;
  return w`<text class="k" x=${x2} y=${y3} text-anchor="middle">air</text><text class="v" x=${x2} y=${y3 + 18} text-anchor="middle">${f1(s4.ambient)}°</text>`;
}
function dtMark(s4, x2, y3) {
  const d3 = s4.pump && s4.power && s4.outlet != null && s4.inlet != null ? s4.outlet - s4.inlet : null;
  const t3 = d3 == null ? "\u2013" : `${d3 >= 0 ? "+" : ""}${f1(d3)}\xB0`;
  return w`<text class="k halo" x=${x2} y=${y3} text-anchor="end">ΔT ${t3}</text>`;
}
function copMark(s4, x2, y3) {
  if (s4.cop == null || s4.cop === 0) return A;
  return w`<text class="k halo" x=${x2} y=${y3} text-anchor="middle">COP ${f1(s4.cop)}</text>`;
}
function circuitSvg(s4, uid = "ph") {
  const yIn = 112, yOut = 76, xPort = 308;
  const L2 = 18, R2 = 183, yRim = 62, yW = 69, yB = 130, r4 = 14;
  const inD = `M${R2} ${yIn} H${xPort}`;
  const outD = `M${xPort} ${yOut} H${R2}`;
  const surface = wave(L2, R2, yW, 2, 11);
  const body = `${surface} V${yB - r4} Q${R2} ${yB} ${R2 - r4} ${yB} H${L2 + r4} Q${L2} ${yB} ${L2} ${yB - r4} Z`;
  const walls = `M${L2} ${yRim} V${yB - r4} Q${L2} ${yB} ${L2 + r4} ${yB} H${R2 - r4} Q${R2} ${yB} ${R2} ${yB - r4} V${yRim}`;
  return b2`<svg class="dwg" viewBox="0 32 420 132">
    <defs><clipPath id="${uid}basin"><rect x=${L2} y=${yRim} width=${R2 - L2} height=${yB - yRim}/></clipPath></defs>
    <path class="water" d=${body}/>
    ${plume(`${uid}pl`, R2 - 6, yOut, 40, 15, body)}
    <path class="wall" d=${walls}/>
    <g clip-path="url(#${uid}basin)"><path class="thin surface" d=${wave(L2 - 11, R2 + 11, yW, 2, 11)}/></g>
    ${airMark(s4, (L2 + R2) / 2, 42)}
    <rect class="ln unitfill" x="304" y="58" width="100" height="72" rx="16"/>
    <circle class="led" cx="394" cy="68" r="2.1"/>
    ${radiator(`${uid}rad`, xPort, yIn, yOut, 40, 6)}
    ${vent(370, 94, 18)}
    ${pipe(inD, "in")}${pipe(outD, "out")}${port(xPort, yIn, "in")}${port(xPort, yOut, "out")}
    ${portLbl(s4, "out", 300, 44, 62)}${portLbl(s4, "in", 300, 134, 152)}${dtMark(s4, 300, 98)}${copMark(s4, 354, 148)}
  </svg>`;
}
function sectionSvg(s4, uid = "ph") {
  const yIn = 86, yOut = 56, xPort = 302;
  const inD = `M208 146 H236 Q250 146 250 132 V100 Q250 ${yIn} 264 ${yIn} H${xPort}`;
  const outD = `M${xPort} ${yOut} H250 Q236 ${yOut} 236 70 V98 Q236 108 222 108 H208`;
  const waterD = "M18 100 H208 V154 H18 Z";
  return b2`<svg class="dwg" viewBox="0 18 420 140">
    <path class="soil" d="M208 96 H420 V154 H208 Z"/>
    <path class="thin grade" d="M0 96 H18"/>
    <rect class="deck-slab" x="208" y="93" width="212" height="5" rx="1"/>
    <path class="water" d=${waterD}/>
    ${plume(`${uid}pl`, 202, 108, 38, 15, waterD)}
    <path class="wall" d="M18 96 V154 H208 V98"/>
    <defs><clipPath id="${uid}basin"><rect x="18" y="96" width="190" height="58"/></clipPath></defs>
    <g clip-path="url(#${uid}basin)"><path class="thin surface" d=${wave(8, 218, 100, 2, 10)}/></g>
    <path class="nozzle out" d="M208 104 L216 108 L208 112 Z"/>
    ${airMark(s4, 113, 70)}
    <rect class="ln unitfill" x="300" y="36" width="98" height="58" rx="12"/>
    <path class="foot" d="M310 94 V96 H320 V94 M378 94 V96 H388 V94"/>
    <circle class="led" cx="388" cy="46" r="2"/>
    ${radiator(`${uid}rad`, xPort, yIn, yOut, 34, 5)}
    ${vent(372, 65, 14.5)}
    ${pipe(inD, "in")}${pipe(outD, "out")}${port(xPort, yIn, "in")}${port(xPort, yOut, "out")}
    ${portLbl(s4, "in", 296, 103, 118)}${portLbl(s4, "out", 296, 32, 47)}${dtMark(s4, 296, 75)}${copMark(s4, 349, 110)}
  </svg>`;
}

// editor.ts
function animationEnabled(config) {
  if (config.animation !== void 0) return config.animation !== false;
  if (config.flow_animation !== void 0) return config.flow_animation !== false;
  return true;
}
function settingsEnabled(config) {
  return config.settings !== false;
}
var PoolHeatPumpCardEditor = class extends i4 {
  constructor() {
    super(...arguments);
    this._config = {};
  }
  setConfig(config) {
    this._config = { schematic: "circuit", ...config };
  }
  change(patch) {
    const next = { ...this._config, ...patch };
    if (patch.animation !== void 0) delete next.flow_animation;
    this._config = next;
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config: this._config } }));
  }
  render() {
    return b2`
      <div class="row">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._config.entity || ""}
          .includeDomains=${["climate"]}
          label="Climate entity"
          @value-changed=${(e4) => this.change({ entity: e4.detail.value })}
        ></ha-entity-picker>
        <ha-select
          label="Schematic"
          .value=${this._config.schematic || "circuit"}
          @selected=${(e4) => {
      const t3 = e4.target;
      if (t3.value) this.change({ schematic: t3.value });
    }}
          @closed=${(e4) => e4.stopPropagation()}
        >
          <ha-list-item value="circuit">Circuit (open basin)</ha-list-item>
          <ha-list-item value="section">Section (cutaway)</ha-list-item>
        </ha-select>
        <ha-formfield alignEnd spaceBetween label="Animation">
          <ha-switch
            .checked=${animationEnabled(this._config)}
            @change=${(e4) => {
      const t3 = e4.target;
      this.change({ animation: t3.checked !== false });
    }}
          ></ha-switch>
        </ha-formfield>
        <ha-formfield alignEnd spaceBetween label="Show heat pump settings">
          <ha-switch
            .checked=${settingsEnabled(this._config)}
            @change=${(e4) => {
      const t3 = e4.target;
      this.change({ settings: t3.checked !== false });
    }}
          ></ha-switch>
        </ha-formfield>
      </div>
    `;
  }
};
PoolHeatPumpCardEditor.styles = i`
    .row { display: grid; gap: 12px; padding: 4px 0 16px; }
    ha-select, ha-entity-picker, ha-formfield { width: 100%; }
  `;
PoolHeatPumpCardEditor.properties = {
  hass: { attribute: false },
  _config: { state: true }
};
var PoolHeatPumpSettingsCardEditor = class extends i4 {
  constructor() {
    super(...arguments);
    this._config = {};
  }
  setConfig(config) {
    this._config = { ...config };
  }
  change(patch) {
    this._config = { ...this._config, ...patch };
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config: this._config } }));
  }
  render() {
    return b2`
      <div class="row">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._config.entity || ""}
          .includeDomains=${["climate"]}
          label="Climate entity"
          @value-changed=${(e4) => this.change({ entity: e4.detail.value })}
        ></ha-entity-picker>
      </div>
    `;
  }
};
PoolHeatPumpSettingsCardEditor.styles = i`
    .row { display: grid; gap: 12px; padding: 4px 0 16px; }
    ha-entity-picker { width: 100%; }
  `;
PoolHeatPumpSettingsCardEditor.properties = {
  hass: { attribute: false },
  _config: { state: true }
};

// parameters.ts
var SERVICE_MENU_RISK = "\u26A0 These service settings can damage or brick the unit. Do not change them unless you know the OEM values.";
var SERVICE_MENU_DISABLED = "Enable changing service settings in the integration options first";
var SERVICE_MENU_OPTIONS_HINT = "\u26A0 Service settings stay locked. Enable them in the integration options only if you know the OEM values \u2014 wrong H/F/D numbers can brick the unit.";
function isAdmin(hass) {
  return hass?.user?.is_admin === true;
}
function emptyParametersView() {
  return { filter: "", group: "", data: null, error: "", busy: false, pending: {} };
}
function fmt(value) {
  if (value === null || value === void 0 || value === "") return "\u2014";
  if (typeof value === "boolean") return value ? "on" : "off";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
function displayValue(row) {
  const text = fmt(row.value);
  return row.unit && text !== "\u2014" ? `${text} ${row.unit}` : text;
}
function matches(row, filter) {
  if (!filter) return true;
  const q = filter.toLowerCase();
  return [row.key, row.label, row.app || "", row.group, String(row.value ?? "")].join(" ").toLowerCase().includes(q);
}
function grouped(payload, filter, only) {
  const wanted = only && only.length ? new Set(only.map(String)) : null;
  const order = payload.groups && payload.groups.length ? payload.groups : [...new Set(payload.parameters.map((r4) => r4.group))];
  const out = [];
  for (const group of order) {
    if (wanted && !wanted.has(group)) continue;
    const rows = payload.parameters.filter((r4) => r4.group === group && matches(r4, filter));
    if (rows.length) out.push([group, rows]);
  }
  return out;
}
async function fetchCatalog(hass, entity, apply) {
  if (!hass.callWS) {
    apply({ error: "WebSocket API unavailable", busy: false });
    return;
  }
  apply({ busy: true, error: "" });
  try {
    const listed = await hass.callWS({ type: "spo_pool_heat_pump/parameters/list", entity_id: entity });
    apply({ data: listed, busy: false, pending: {} });
    const refreshed = await hass.callWS({ type: "spo_pool_heat_pump/parameters/refresh", entity_id: entity });
    if (refreshed?.parameters) apply({ data: refreshed, busy: false, pending: {} });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}
async function commitParameter(hass, entity, row, value, view, apply, riskOk) {
  if (row.tier === "service_menu") {
    if (!view.data?.service_menu_writes) {
      apply({ error: SERVICE_MENU_DISABLED });
      return false;
    }
    if (!riskOk.current && !window.confirm(SERVICE_MENU_RISK)) return false;
    riskOk.current = true;
  }
  if (!hass.callWS) {
    apply({ error: "WebSocket API unavailable" });
    return false;
  }
  apply({ busy: true, error: "" });
  try {
    const data = await hass.callWS({
      type: "spo_pool_heat_pump/parameters/set",
      entity_id: entity,
      key: row.key,
      value
    });
    const patched = data.parameters ? {
      ...data,
      parameters: data.parameters.map((item) => item.key === row.key ? { ...item, value } : item)
    } : data;
    apply({ data: patched, busy: false, pending: {} });
    return true;
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
    return false;
  }
}
function renderParameterBrowser(args) {
  const view = args.view;
  const groups = view.data ? grouped(view.data, view.filter, args.config.parameters_groups) : [];
  const selected = view.group && groups.some(([name]) => name === view.group) ? view.group : groups[0]?.[0] || "";
  const rows = groups.find(([name]) => name === selected)?.[1] || [];
  const locked = view.data && !view.data.service_menu_writes;
  return b2`
    <div class="params-browser">
      <input
        class="params-filter"
        type="search"
        placeholder="Filter"
        .value=${view.filter}
        @input=${(e4) => args.onFilter(e4.target.value)}
      />
      ${groups.length > 1 ? b2`<select
            class="params-groups"
            .value=${selected}
            @change=${(e4) => args.onGroup(e4.target.value)}
          >
            ${groups.map(([group, items]) => b2`<option value=${group} ?selected=${group === selected}>${items[0]?.group_label || group} (${items.length})</option>`)}
          </select>` : ""}
      ${locked ? b2`<div class="params-note">${SERVICE_MENU_OPTIONS_HINT}</div>` : ""}
      ${view.busy ? b2`<div class="params-note">Reading…</div>` : ""}
      ${view.error ? b2`<div class="params-error">${view.error}</div>` : ""}
      ${view.data ? b2`<div class="params-count">${view.data.parameters.length} parameters${selected ? ` \xB7 ${groups.find(([name]) => name === selected)?.[1][0]?.group_label || selected}` : ""}</div>` : ""}
      <div class="params-rows">
        ${rows.map((row) => renderRow(row, view, args.onCommit, args.onPending))}
      </div>
    </div>
  `;
}
function renderRow(row, view, onCommit, onPending) {
  const left = row.app ? `${row.label} \xB7 ${row.app}` : row.label;
  const locked = row.tier === "readonly" || row.tier === "service_menu" && !view.data?.service_menu_writes;
  const reason = row.tier === "service_menu" && !view.data?.service_menu_writes ? SERVICE_MENU_DISABLED : "";
  if (locked) {
    return b2`<div class="params-row ${row.tier}">
      <span class="params-label" title=${reason || row.key}>${left}</span>
      <span class="params-val" title=${reason}>${displayValue(row)}</span>
    </div>`;
  }
  const pending = view.pending[row.key];
  const current = pending !== void 0 ? pending : row.value == null ? "" : String(row.value);
  if (row.options && row.options.length && row.type !== "u16") {
    return b2`<div class="params-row ${row.tier}">
      <span class="params-label">${left}</span>
      <select
        class="params-input"
        .value=${current}
        @change=${(e4) => onCommit(row, e4.target.value)}
      >
        ${row.options.map((opt) => b2`<option value=${opt} ?selected=${String(row.value) === opt}>${opt}</option>`)}
      </select>
    </div>`;
  }
  if (row.type === "bool") {
    const on = current === "true" || current === "on" || current === "1";
    return b2`<div class="params-row ${row.tier}">
      <span class="params-label">${left}</span>
      <select class="params-input" .value=${on ? "true" : "false"}
        @change=${(e4) => onCommit(row, e4.target.value === "true")}>
        <option value="false">off</option>
        <option value="true">on</option>
      </select>
    </div>`;
  }
  return b2`<div class="params-row ${row.tier}">
    <span class="params-label">${left}</span>
    <span class="params-edit">
      <input
        class="params-input"
        type="number"
        step=${row.step ?? 1}
        min=${row.min ?? ""}
        max=${row.max ?? ""}
        .value=${current}
        @input=${(e4) => onPending(row.key, e4.target.value)}
        @change=${(e4) => onCommit(row, e4.target.value)}
        @keydown=${(e4) => {
    if (e4.key === "Enter") onCommit(row, e4.target.value);
  }}
      />
      ${row.unit ? b2`<small>${row.unit}</small>` : ""}
    </span>
  </div>`;
}

// dump.ts
function emptyDumpView() {
  return {
    pane: "params",
    minutes: 15,
    untilStop: false,
    note: "",
    includeWrites: true,
    helpOpen: false,
    status: null,
    error: "",
    busy: false
  };
}
function mb(bytes) {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function fmtTime(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return "\u2014";
  const s4 = Math.max(0, Math.round(seconds));
  const m2 = Math.floor(s4 / 60);
  const r4 = s4 % 60;
  return m2 ? `${m2}m ${r4}s` : `${r4}s`;
}
async function callDump(hass, type, extra = {}) {
  if (!hass.callWS) throw new Error("WebSocket unavailable");
  return hass.callWS({ type, ...extra });
}
async function fetchDumpStatus(hass, entity, apply) {
  try {
    const status = await callDump(hass, "spo_pool_heat_pump/dump/status", { entity_id: entity });
    apply({ status, error: "" });
  } catch (err) {
    apply({ error: err instanceof Error ? err.message : String(err) });
  }
}
async function startDump(hass, entity, view, apply) {
  apply({ busy: true, error: "" });
  try {
    const minutes = Math.min(120, Math.max(1, Number(view.minutes) || 15));
    const status = await callDump(hass, "spo_pool_heat_pump/dump/start", {
      entity_id: entity,
      duration_s: view.untilStop ? 0 : minutes * 60,
      note: view.note,
      include_writes: view.includeWrites
    });
    apply({ status, busy: false });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}
async function stopDump(hass, entity, apply) {
  apply({ busy: true, error: "" });
  try {
    const status = await callDump(hass, "spo_pool_heat_pump/dump/stop", { entity_id: entity });
    apply({ status, busy: false });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}
async function deleteDump(hass, entity, name, apply) {
  if (!window.confirm(`Delete ${name} and its .bin?`)) return;
  apply({ busy: true, error: "" });
  try {
    const status = await callDump(hass, "spo_pool_heat_pump/dump/delete", { entity_id: entity, name });
    apply({ status, busy: false });
  } catch (err) {
    apply({ busy: false, error: err instanceof Error ? err.message : String(err) });
  }
}
async function downloadDump(hass, name) {
  const token = hass.auth?.data?.access_token;
  const resp = await fetch(`/api/spo_pool_heat_pump/dumps/${encodeURIComponent(name)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });
  if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}
function renderDumpPanel(args) {
  const view = args.view;
  const st = view.status;
  const limits = st?.limits;
  const running = Boolean(st?.running);
  return b2`
    <div class="dump-panel">
      <div class="dump-head">
        <span class="dump-title">What to capture</span>
        <button class="dump-help-btn ${view.helpOpen ? "on" : ""}" title="What is a bus dump?" aria-label="What is a bus dump?" aria-expanded=${view.helpOpen} @click=${args.onHelp}>?</button>
      </div>
      ${view.helpOpen ? b2`
        <div class="dump-help">
          <p>This records the raw RS-485 bytes Home Assistant sees on the DR164 — the same format we used to map the Cosma. A later dump is how a new model or an unknown register gets decoded.</p>
          <p><strong>Start the capture first</strong>, then act. Write in the note what you are about to do. One action at a time; wait a few seconds so the frames stay separable.</p>
          <p>Use the <strong>heat-pump panel and the phone app</strong> if both exist. They write different registers (panel vs DTU slave 99). Leave the factory WiFi / DTU plugged in.</p>
          <p><strong>Screenshot the phone app</strong> after each change (the page you just used), or <strong>photo the heat-pump display</strong> if there is no app or the change was on the panel. The picture should show the menu name and the value (H03, target 28 °C, Quiet on). Name files with clock time or the dump note so they line up with timestamps in the <code>.log</code>. One photo per action. Attach those images with the downloaded log when asking for a new profile or an unknown register.</p>
          <p>Work through everything that should appear on the wire:</p>
          <ul>
            <li>Power on and off.</li>
            <li>Heat, Cool, Auto — then change the target in each mode (they keep separate setpoints).</li>
            <li>Quiet / quiet timer, and the on/off timers.</li>
            <li>Every on-screen menu (H, F, D, E, P, R, timers). Open each page. Change a value, wait, put it back if you do not want to keep it.</li>
            <li>Screenshot / photo after every change.</li>
            <li>Let the unit actually run: pump pre-run, compressor start, reach the setpoint, go idle. Cooling as well as heating if the unit can.</li>
          </ul>
          <p>Do not change H/F/D service values unless you know the OEM numbers — those can damage the unit. Then download the <code>.log</code>.</p>
        </div>
      ` : ""}
      ${running ? b2`
            <div class="params-note">
              Recording · ${mb(st?.bytes || 0)} · ${fmtTime(st?.elapsed_s)}
              ${st?.duration_s ? b2` · ${fmtTime(st.remaining_s)} left` : b2` · until stop`}
            </div>
            <button class="dump-btn" ?disabled=${view.busy} @click=${args.onStop}>Stop now</button>
          ` : b2`
            <label class="dump-field">Duration (minutes)
              <input
                class="params-input dump-minutes"
                type="number"
                min="1"
                max="120"
                .value=${String(view.minutes)}
                ?disabled=${view.untilStop}
                @change=${(e4) => args.onMinutes(Number(e4.target.value))}
              />
            </label>
            <label class="dump-check">
              <input type="checkbox" .checked=${view.untilStop} @change=${(e4) => args.onUntilStop(e4.target.checked)} />
              Until I stop
            </label>
            <label class="dump-field">Note
              <input class="params-filter" type="text" maxlength="200" .value=${view.note} @input=${(e4) => args.onNote(e4.target.value)} />
            </label>
            <label class="dump-check">
              <input type="checkbox" .checked=${view.includeWrites} @change=${(e4) => args.onWrites(e4.target.checked)} />
              Include HA writes
            </label>
            <button class="dump-btn" ?disabled=${view.busy} @click=${args.onStart}>Start capture</button>
          `}
      ${view.error ? b2`<div class="params-error">${view.error}</div>` : ""}
      <div class="params-note">
        Timed run 1–120 min. Until I stop still ends at ${mb(limits?.session_cap_bytes || 40 * 1024 * 1024)}
        (${mb(limits?.rotate_bytes || 8 * 1024 * 1024)} × ${limits?.keep_files || 5} files).
        Dumps folder ${mb(limits?.dir_used || 0)} / ${mb(limits?.dir_cap_bytes || 200 * 1024 * 1024)}.
        One dump at a time.
      </div>
      <div class="params-count">${st?.files?.length || 0} captures</div>
      <div class="dump-files">
        ${(st?.files || []).map(
    (file) => b2`
            <div class="dump-file">
              <div>
                <div class="params-label">${file.name}</div>
                <div class="params-note">${mb(file.size)}${file.note ? ` \xB7 ${file.note}` : ""}${file.started ? ` \xB7 ${file.started}` : ""}</div>
              </div>
              <div class="dump-actions">
                <button class="dump-link" @click=${() => args.onDownload(file.name)}>Download log</button>
                ${file.bin ? b2`<button class="dump-link" @click=${() => args.onDownload(file.bin)}>Download bin</button>` : ""}
                <button class="dump-link" @click=${() => args.onDelete(file.name)}>Delete</button>
              </div>
            </div>
          `
  )}
      </div>
      <div class="params-note">
        Feed the .log into analyze_modbus.py or dump_replay_server.py.
      </div>
    </div>
  `;
}

// settings-panel.ts
var ParameterHost = class {
  constructor() {
    this.view = emptyParametersView();
    this.risk = { current: false };
    this._gen = 0;
  }
  apply(host, patch) {
    host._params = { ...host._params, ...patch };
    this.view = host._params;
  }
  load(hass, entity, host) {
    if (!hass || !entity) return;
    const g2 = ++this._gen;
    void fetchCatalog(hass, entity, (patch) => {
      if (g2 !== this._gen) return;
      this.apply(host, patch);
    });
  }
  commit(hass, entity, host, row, value) {
    if (!hass || !entity) return;
    void commitParameter(hass, entity, row, value, host._params, (patch) => this.apply(host, patch), this.risk);
  }
};
var SettingsPanel = class {
  constructor() {
    this.timer = null;
    this._gen = 0;
  }
  applyDump(host, patch) {
    host._dump = { ...host._dump, ...patch };
  }
  applyDumpIf(host, g2, patch) {
    if (g2 !== this._gen) return;
    this.applyDump(host, patch);
  }
  refreshDump(host) {
    if (!host.hass || !host._config.entity) return;
    const g2 = this._gen;
    void fetchDumpStatus(host.hass, host._config.entity, (patch) => this.applyDumpIf(host, g2, patch));
  }
  startPoll(host) {
    if (this.timer != null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
    this.timer = window.setInterval(() => {
      if (host._dump.pane === "dump" || host._dump.status?.running) this.refreshDump(host);
    }, 2e3);
  }
  stopPoll() {
    this._gen++;
    if (this.timer != null) {
      window.clearInterval(this.timer);
      this.timer = null;
    }
  }
  tabs(host) {
    return b2`
      <div class="settings-tabs">
        <button class=${host._dump.pane === "params" ? "on" : ""} @click=${() => this.applyDump(host, { pane: "params" })}>Parameters</button>
        <button class=${host._dump.pane === "dump" ? "on" : ""} @click=${() => {
      this.applyDump(host, { pane: "dump" });
      this.refreshDump(host);
    }}>Bus dump</button>
      </div>
    `;
  }
  body(host) {
    if (host._dump.pane === "dump") {
      return renderDumpPanel({
        view: host._dump,
        onMinutes: (value) => this.applyDump(host, { minutes: value }),
        onUntilStop: (value) => this.applyDump(host, { untilStop: value }),
        onNote: (value) => this.applyDump(host, { note: value }),
        onWrites: (value) => this.applyDump(host, { includeWrites: value }),
        onHelp: () => this.applyDump(host, { helpOpen: !host._dump.helpOpen }),
        onStart: () => {
          if (!host.hass || !host._config.entity) return;
          const g2 = this._gen;
          void startDump(host.hass, host._config.entity, host._dump, (patch) => this.applyDumpIf(host, g2, patch));
        },
        onStop: () => {
          if (!host.hass || !host._config.entity) return;
          const g2 = this._gen;
          void stopDump(host.hass, host._config.entity, (patch) => this.applyDumpIf(host, g2, patch));
        },
        onDelete: (name) => {
          if (!host.hass || !host._config.entity) return;
          const g2 = this._gen;
          void deleteDump(host.hass, host._config.entity, name, (patch) => this.applyDumpIf(host, g2, patch));
        },
        onDownload: (name) => {
          if (!host.hass) return;
          const g2 = this._gen;
          void downloadDump(host.hass, name).catch((err) => this.applyDumpIf(host, g2, { error: String(err) }));
        }
      });
    }
    return renderParameterBrowser({
      config: host._config,
      view: host._params,
      onFilter: (value) => {
        host._params = { ...host._params, filter: value };
      },
      onGroup: (value) => {
        host._params = { ...host._params, group: value };
      },
      onCommit: (row, value) => host._host.commit(host.hass, host._config.entity, host, row, value),
      onPending: (key, value) => {
        host._params = { ...host._params, pending: { ...host._params.pending, [key]: value } };
      }
    });
  }
};

// card.ts
var styles = `${host_default}
${wave3_default}`;
var NUDGE_DEBOUNCE_MS = 1e3;
var NUDGE_STICK_MS = 5e3;
var MINUS = b2`<svg viewBox="0 0 24 24"><path d="M6 12h12"/></svg>`;
var PLUS = b2`<svg viewBox="0 0 24 24"><path d="M12 6v12M6 12h12"/></svg>`;
var PW = b2`<svg viewBox="0 0 24 24"><path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/></svg>`;
var FEATHER = b2`<svg viewBox="0 0 24 24"><path d="M20.2 12.2a6 6 0 0 0-8.5-8.5L5 10.5V19h8.5z"/><path d="M16 8 2 22"/><path d="M17.5 15H9"/></svg>`;
var TUNE = b2`<svg viewBox="0 0 24 24"><path d="M4 8h9M17 8h3"/><circle cx="15" cy="8" r="2"/><path d="M4 16h3M11 16h9"/><circle cx="9" cy="16" r="2"/></svg>`;
var STATUS_ACTION = {
  "Warming up": "warmup",
  Starting: "precool",
  Heating: "heating",
  Cooling: "cooling",
  Off: "off",
  "Dump only": "off"
};
function num(st) {
  if (!st || st.state === "unavailable" || st.state === "unknown") return null;
  const n4 = Number(st.state);
  return Number.isFinite(n4) ? n4 : null;
}
function firstClimate(hass) {
  return Object.keys(hass.states || {}).find((id) => id.startsWith("climate.") && hass.entities?.[id]?.platform === "spo_pool_heat_pump") || Object.keys(hass.states || {}).find((id) => id.startsWith("climate."));
}
var PoolHeatPumpCard = class extends i4 {
  constructor() {
    super(...arguments);
    this._config = {};
    this._params = emptyParametersView();
    this._dump = emptyDumpView();
    this._dialogOpen = false;
    this._targetLocal = null;
    this._svgId = `ph${Math.random().toString(36).slice(2, 8)}`;
    this._host = new ParameterHost();
    this._settings = new SettingsPanel();
    this._sibIds = [];
    this._nudgeTimer = null;
    this._nudgeClearTimer = null;
  }
  static getConfigElement() {
    return document.createElement("spo-pool-heat-pump-card-editor");
  }
  static getStubConfig(hass) {
    const stub = {
      type: "custom:spo-pool-heat-pump-card",
      schematic: "circuit",
      animation: true,
      settings: true
    };
    const climate = firstClimate(hass);
    if (climate) stub.entity = climate;
    return stub;
  }
  setConfig(config) {
    this._config = { schematic: "circuit", ...config };
  }
  getCardSize() {
    return 6;
  }
  getGridOptions() {
    return { columns: 12, rows: 8, min_columns: 6, min_rows: 6 };
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._nudgeTimer != null) {
      window.clearTimeout(this._nudgeTimer);
      this._nudgeTimer = null;
      if (this._targetLocal != null) {
        this.call("climate", "set_temperature", { temperature: this._targetLocal });
      }
    }
    if (this._nudgeClearTimer != null) {
      window.clearTimeout(this._nudgeClearTimer);
      this._nudgeClearTimer = null;
    }
    this._settings.stopPoll();
  }
  shouldUpdate(changed) {
    if (changed.has("_config") || changed.has("_params") || changed.has("_dialogOpen") || changed.has("_targetLocal") || changed.has("_dump")) {
      return true;
    }
    if (changed.has("hass")) {
      return this._hassRelevantChanged(changed.get("hass"), this.hass);
    }
    return true;
  }
  willUpdate(_changed) {
    if (this._targetLocal == null) return;
    const climate = this.hass?.states[this._config.entity || ""];
    const ha = Number(climate?.attributes.temperature ?? NaN);
    const step = Number(climate?.attributes.target_temp_step ?? 0.5) || 0.5;
    if (Number.isFinite(ha) && Math.abs(ha - this._targetLocal) < step / 2) {
      this._targetLocal = null;
      if (this._nudgeClearTimer != null) {
        window.clearTimeout(this._nudgeClearTimer);
        this._nudgeClearTimer = null;
      }
    }
  }
  _hassRelevantChanged(oldHass, hass) {
    if (!oldHass || !hass) return true;
    if (oldHass.user !== hass.user || oldHass.entities !== hass.entities) return true;
    const entity = this._config.entity;
    if (!entity) return oldHass.states !== hass.states;
    for (const id of [entity, ...this.siblingIds(hass, entity)]) {
      if (oldHass.states[id] !== hass.states[id]) return true;
    }
    return false;
  }
  /** Sibling ids from the entity registry; cached until hass.entities is replaced. */
  siblingIds(hass, entityId) {
    const entities = hass.entities;
    const device = entities?.[entityId]?.device_id;
    if (!device) return [];
    if (this._sibEntities === entities && this._sibDevice === device) return this._sibIds;
    const ids = [];
    for (const [eid, em] of Object.entries(entities || {})) {
      if (em?.device_id === device) ids.push(eid);
    }
    this._sibEntities = entities;
    this._sibDevice = device;
    this._sibIds = ids;
    return ids;
  }
  siblings(hass, entityId) {
    const out = {};
    for (const eid of this.siblingIds(hass, entityId)) {
      const st = hass.states[eid];
      if (!st) continue;
      const em = hass.entities?.[eid];
      out[em?.translation_key || eid.split(".").pop() || eid] = st;
    }
    return out;
  }
  view() {
    const hass = this.hass;
    const entity = this._config.entity;
    if (!hass || !entity) return null;
    const climate = hass.states[entity];
    if (!climate) return null;
    const sib = this.siblings(hass, entity);
    const available = climate.state !== "unavailable";
    const mode = climate.state === "heat_cool" ? "auto" : climate.state;
    const power = available && climate.state !== "off";
    const silent = climate.attributes.preset_mode === "silent";
    const faultSt = sib.fault;
    const fault = faultSt?.state === "on" ? String(faultSt.attributes.code || climate.attributes.fault || "fault") : climate.attributes.fault ? String(climate.attributes.fault) : null;
    const faultText = fault ? String(climate.attributes.fault_text || faultSt?.attributes.text || "") : "";
    const liveInlet = Number(climate.attributes.current_temperature ?? NaN);
    const sensorInlet = num(sib.inlet);
    const inlet = sensorInlet ?? (Number.isFinite(liveInlet) ? liveInlet : null);
    const outlet = num(sib.outlet);
    const ambient = num(sib.ambient);
    const haSetpoint = Number(climate.attributes.temperature ?? NaN);
    const setpoint = this._targetLocal ?? (Number.isFinite(haSetpoint) ? haSetpoint : NaN);
    const kw = num(sib.power);
    const kwh24 = num(sib.energy_24h);
    const pct = num(sib.compressor);
    const fanRpm = num(sib.fan);
    const caps = {
      cool: Array.isArray(climate.attributes.hvac_modes) && climate.attributes.hvac_modes.includes("cool"),
      auto: Array.isArray(climate.attributes.hvac_modes) && climate.attributes.hvac_modes.includes("heat_cool"),
      silent: Array.isArray(climate.attributes.preset_modes) && climate.attributes.preset_modes.includes("silent"),
      power: kw != null,
      energy: kwh24 != null,
      compressor: pct != null,
      ambient: ambient != null,
      fan: fanRpm != null
    };
    const status = !available ? "No data" : String(climate.attributes.activity || "No data");
    const action = STATUS_ACTION[status] || "idle";
    const pump = sib.pump_running ? sib.pump_running.state === "on" : action === "heating" || action === "cooling" || action === "warmup" || action === "precool";
    return {
      available,
      power,
      mode,
      action,
      inlet: inlet != null && Number.isFinite(inlet) ? inlet : null,
      inletLive: Number.isFinite(liveInlet) ? liveInlet : inlet != null && Number.isFinite(inlet) ? inlet : null,
      outlet,
      ambient,
      setpoint: Number.isFinite(setpoint) ? setpoint : null,
      kw,
      kwh24,
      pct,
      fanRpm,
      silent,
      pump,
      fault,
      faultText: faultText || null,
      status,
      cop: (() => {
        const raw = Number(climate.attributes.cop);
        return Number.isFinite(raw) && raw !== 0 ? raw : null;
      })(),
      dumpOnly: climate.attributes.dump_only === true || status === "Dump only",
      caps
    };
  }
  call(domain, service, data) {
    this.hass?.callService(domain, service, { entity_id: this._config.entity, ...data });
  }
  setMode(mode) {
    const hvac = mode === "auto" ? "heat_cool" : mode;
    this.call("climate", "set_hvac_mode", { hvac_mode: hvac });
  }
  nudge(delta) {
    const climate = this.hass?.states[this._config.entity || ""];
    const min = Number(climate?.attributes.min_temp ?? 8);
    const max = Number(climate?.attributes.max_temp ?? 40);
    const step = Number(climate?.attributes.target_temp_step ?? 0.5) || 0.5;
    const current = this._targetLocal ?? Number(climate?.attributes.temperature ?? NaN);
    if (!Number.isFinite(current)) return;
    const stepped = Math.round((current + delta) / step) * step;
    this._targetLocal = Math.min(max, Math.max(min, stepped));
    if (this._nudgeClearTimer != null) {
      window.clearTimeout(this._nudgeClearTimer);
      this._nudgeClearTimer = null;
    }
    if (this._nudgeTimer != null) window.clearTimeout(this._nudgeTimer);
    this._nudgeTimer = window.setTimeout(() => {
      this._nudgeTimer = null;
      if (this._targetLocal == null) return;
      this.call("climate", "set_temperature", { temperature: this._targetLocal });
      this._nudgeClearTimer = window.setTimeout(() => {
        this._nudgeClearTimer = null;
        this._targetLocal = null;
      }, NUDGE_STICK_MS);
    }, NUDGE_DEBOUNCE_MS);
  }
  openSettings() {
    this._dialogOpen = true;
    if (this.view()?.dumpOnly) {
      this._dump = { ...this._dump, pane: "dump" };
    }
    this._host.load(this.hass, this._config.entity, this);
    this._settings.refreshDump(this);
    this._settings.startPoll(this);
  }
  closeSettings() {
    this._dialogOpen = false;
    this._settings.stopPoll();
  }
  openMoreInfo() {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId: this._config.entity }
      })
    );
  }
  render() {
    const s4 = this.view();
    if (!s4) return b2`<ha-card class="card"><div class="w3">No climate entity</div></ha-card>`;
    const f3 = flow(s4);
    const schematic = this._config.schematic === "section" ? "section" : "circuit";
    const drawing = schematic === "section" ? sectionSvg(s4, this._svgId) : circuitSvg(s4, this._svgId);
    const facts = [];
    if (s4.caps.power) facts.push(["Power", f1(s4.kw), "kW"]);
    if (s4.caps.energy) facts.push(["Last 24 h", f1(s4.kwh24), "kWh"]);
    if (s4.caps.compressor) facts.push(["Compressor", String(s4.pct ?? "\u2013"), "%"]);
    if (s4.caps.fan) facts.push(["Fan", s4.fanRpm == null ? "\u2013" : String(s4.fanRpm), "rpm"]);
    const modes = ["heat", ...s4.caps.auto ? ["auto"] : [], ...s4.caps.cool ? ["cool"] : []];
    const showTune = settingsEnabled(this._config) && isAdmin(this.hass);
    return b2`
      <ha-card class="card ${schematic}"
        data-available=${s4.available}
        data-action=${s4.available && s4.power ? s4.action === "warmup" ? "heating" : s4.action === "precool" ? "cooling" : s4.action : "off"}
        data-pump=${s4.pump && s4.power && s4.available}
        data-silent=${s4.silent}
        data-flow=${animationEnabled(this._config)}
        style=${`--inC:${f3.inC};--outC:${f3.outC};--accent:${accent(s4)};`}>
        <div class="w3 ${schematic}">
          <div class="top">
            <span class="eyebrow" @click=${() => this.openMoreInfo()}>Pool temperature</span>
            <div class="status-block">
              <span class="eyebrow status"><i></i>${s4.status}</span>
              ${s4.fault && s4.faultText ? b2`<span class="fault-why">${s4.faultText}</span>` : ""}
            </div>
          </div>
          <div class="hero">
            <div class="big"><span class="num">${f1(s4.inletLive ?? s4.inlet)}</span><span class="unit">°C</span></div>
            ${s4.dumpOnly ? b2`<div class="target"><span class="eyebrow">No map</span><span class="val">Use Settings → Bus dump</span></div>` : b2`<div class="target">
              <span class="eyebrow">Target</span>
              <button class="ib" title="Lower target" @click=${() => this.nudge(-0.5)}>${MINUS}</button>
              <span class="val"><span class="num">${f1(s4.setpoint)}</span><span class="unit">°</span></span>
              <button class="ib" title="Raise target" @click=${() => this.nudge(0.5)}>${PLUS}</button>
            </div>`}
          </div>
          ${drawing}
          <div class="facts">${facts.map(([k2, v2, u3]) => b2`<div class="fact"><div class="v">${v2}<small>${u3}</small></div><span class="eyebrow">${k2}</span></div>`)}</div>
          <div class="modes">
            ${s4.dumpOnly ? "" : b2`<div class="seg">${modes.map((m2) => b2`<button class=${s4.power && s4.mode === m2 ? "on" : ""} @click=${() => this.setMode(m2)}>${m2 === "heat" ? "Heat" : m2 === "cool" ? "Cool" : "Auto"}</button>`)}</div>`}
            <span class="sp"></span>
            ${showTune ? b2`<button class="ib params-open" title="Heat pump settings" @click=${() => this.openSettings()}>${TUNE}</button>` : ""}
            ${s4.dumpOnly || !s4.caps.silent ? "" : b2`<button class="ib quiet ${s4.silent ? "on" : ""}" title="Quiet mode"
              @click=${() => this.call("climate", "set_preset_mode", { preset_mode: s4.silent ? "none" : "silent" })}>${FEATHER}</button>`}
            ${s4.dumpOnly ? "" : b2`<button class="ib pw ${s4.power ? "on" : ""}" title="Power"
              @click=${() => this.call("climate", s4.power ? "turn_off" : "turn_on", {})}>${PW}</button>`}
          </div>
          ${s4.available ? "" : b2`<div class="stale"><span><i></i>No data from heat pump for 8 s</span></div>`}
        </div>
      </ha-card>
      ${this._dialogOpen ? b2`
        <ha-dialog open hideActions @closed=${() => this.closeSettings()}>
          <span slot="heading">Settings</span>
          ${this._settings.tabs(this)}
          ${this._settings.body(this)}
        </ha-dialog>
      ` : ""}
    `;
  }
};
PoolHeatPumpCard.styles = r(styles);
PoolHeatPumpCard.properties = {
  hass: { attribute: false },
  _config: { state: true },
  _params: { state: true },
  _dialogOpen: { state: true },
  _targetLocal: { state: true },
  _dump: { state: true }
};
var PoolHeatPumpSettingsCard = class extends i4 {
  constructor() {
    super(...arguments);
    this._config = {};
    this._params = emptyParametersView();
    this._dump = emptyDumpView();
    this._host = new ParameterHost();
    this._settings = new SettingsPanel();
    this._loadedFor = "";
  }
  static getConfigElement() {
    return document.createElement("spo-pool-heat-pump-settings-card-editor");
  }
  static getStubConfig(hass) {
    const stub = { type: "custom:spo-pool-heat-pump-settings-card" };
    const climate = firstClimate(hass);
    if (climate) stub.entity = climate;
    return stub;
  }
  setConfig(config) {
    this._config = { ...config };
    this._loadedFor = "";
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    this._settings.stopPoll();
  }
  getCardSize() {
    return 12;
  }
  getGridOptions() {
    return { columns: 12, rows: 12, min_columns: 6, min_rows: 4 };
  }
  updated() {
    const entity = this._config.entity || "";
    if (!isAdmin(this.hass) || !this.hass || !entity || this._loadedFor === entity) return;
    this._settings.stopPoll();
    this._loadedFor = entity;
    this._host.load(this.hass, entity, this);
    this._settings.refreshDump(this);
    this._settings.startPoll(this);
  }
  render() {
    if (!isAdmin(this.hass)) {
      return b2`<ha-card class="params-card"><div class="w3">Administrator only</div></ha-card>`;
    }
    if (!this._config.entity) {
      return b2`<ha-card class="params-card"><div class="w3">No climate entity</div></ha-card>`;
    }
    return b2`
      <ha-card class="params-card">
        <div class="params-card-head">
          <span class="eyebrow">Settings</span>
          <button class="params-refresh" ?disabled=${this._params.busy} @click=${() => {
      this._loadedFor = "";
      this._host.load(this.hass, this._config.entity, this);
      this._settings.refreshDump(this);
    }}>Refresh</button>
        </div>
        ${this._settings.tabs(this)}
        ${this._settings.body(this)}
      </ha-card>
    `;
  }
};
PoolHeatPumpSettingsCard.styles = r(styles);
PoolHeatPumpSettingsCard.properties = {
  hass: { attribute: false },
  _config: { state: true },
  _params: { state: true },
  _dump: { state: true }
};
function defineEl(name, ctor) {
  if (!customElements.get(name)) customElements.define(name, ctor);
}
defineEl("spo-pool-heat-pump-card", PoolHeatPumpCard);
defineEl("spo-pool-heat-pump-card-editor", PoolHeatPumpCardEditor);
defineEl("spo-pool-heat-pump-settings-card", PoolHeatPumpSettingsCard);
defineEl("spo-pool-heat-pump-settings-card-editor", PoolHeatPumpSettingsCardEditor);
function getEntitySuggestion(hass, entityId) {
  if (!entityId.startsWith("climate.")) return null;
  const platform = hass.entities?.[entityId]?.platform;
  if (platform && platform !== "spo_pool_heat_pump") return null;
  return {
    config: {
      type: "custom:spo-pool-heat-pump-card",
      entity: entityId,
      schematic: "circuit",
      animation: true,
      settings: true
    }
  };
}
var win = window;
win.customCards = win.customCards || [];
win.customCards.push({
  type: "spo-pool-heat-pump-card",
  name: "SPO Pool Heat Pump",
  description: "Circuit / section schematic for the SPO Pool Heat Pump climate entity",
  preview: true,
  getEntitySuggestion
});
win.customCards.push({
  type: "spo-pool-heat-pump-settings-card",
  name: "SPO Pool Heat Pump settings",
  description: "Full register and service-menu catalog for a SPO Pool Heat Pump climate entity",
  preview: false
});
/*! Bundled license information:

@lit/reactive-element/css-tag.js:
  (**
   * @license
   * Copyright 2019 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

@lit/reactive-element/reactive-element.js:
lit-html/lit-html.js:
lit-element/lit-element.js:
  (**
   * @license
   * Copyright 2017 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)

lit-html/is-server.js:
  (**
   * @license
   * Copyright 2022 Google LLC
   * SPDX-License-Identifier: BSD-3-Clause
   *)
*/
