/* ============================================
   GRND Consulting — Interactions
   ui-ux-pro-max: §1 accessibility, §2 interaction,
                  §7 animation, §8 forms
   ============================================ */

(function () {
  'use strict';

  // ============================================================
  // CONTACT FORM DELIVERY — paste your Web3Forms access key here.
  // Get one free in ~30s at https://web3forms.com (enter
  // notification@staygrnd.xyz, they email you the key). Submissions
  // are then delivered to that inbox. Until a key is set, the form
  // falls back to WhatsApp/email so visitors are never stranded.
  // ============================================================
  var WEB3FORMS_ACCESS_KEY = 'YOUR-ACCESS-KEY-HERE';

  var WHATSAPP_URL = 'https://wa.me/60126274178';
  var CONTACT_EMAIL = 'notification@staygrnd.xyz';

  // --- Respect prefers-reduced-motion (skill: §2 reduced-motion) ---
  var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // --- Dynamic footer year ---
  var yearEl = document.getElementById('footerYear');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // --- Nav scroll effect ---
  var nav = document.getElementById('nav');

  function onScroll() {
    nav.classList.toggle('nav--scrolled', window.scrollY > 40);
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // --- Mobile menu (skill: §9 modal-escape, aria-expanded) ---
  var burger      = document.getElementById('burger');
  var mobileMenu  = document.getElementById('mobileMenu');
  var mobileClose = document.getElementById('mobileClose');

  function openMenu() {
    mobileMenu.classList.add('open');
    burger.setAttribute('aria-expanded', 'true');
    burger.setAttribute('aria-label', 'Close menu');
    document.body.style.overflow = 'hidden';
    mobileClose.focus();
  }

  function closeMenu() {
    mobileMenu.classList.remove('open');
    burger.setAttribute('aria-expanded', 'false');
    burger.setAttribute('aria-label', 'Open menu');
    document.body.style.overflow = '';
    burger.focus();
  }

  burger.addEventListener('click', function () {
    mobileMenu.classList.contains('open') ? closeMenu() : openMenu();
  });

  mobileClose.addEventListener('click', closeMenu);

  // Close on link click
  mobileMenu.querySelectorAll('a').forEach(function (link) {
    link.addEventListener('click', closeMenu);
  });

  // Close on Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && mobileMenu.classList.contains('open')) {
      closeMenu();
    }
  });

  // --- Scroll reveal with stagger (skill: §7 stagger-sequence) ---
  var reveals = document.querySelectorAll('.reveal');

  if (!prefersReducedMotion && 'IntersectionObserver' in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );

    reveals.forEach(function (el) {
      observer.observe(el);
    });
  } else {
    // Reduced motion or no IO support — show everything immediately
    reveals.forEach(function (el) {
      el.classList.add('visible');
    });
  }

  // --- Smooth scroll for anchor links (skill: §9 smooth scroll) ---
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      var href = this.getAttribute('href');
      if (href === '#') return;
      var target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        var offsetTop = target.getBoundingClientRect().top + window.scrollY - 80;
        if (prefersReducedMotion) {
          window.scrollTo({ top: offsetTop });
        } else {
          window.scrollTo({ top: offsetTop, behavior: 'smooth' });
        }
        // Move focus to section for keyboard/screen-reader users
        target.setAttribute('tabindex', '-1');
        target.focus({ preventScroll: true });
      }
    });
  });

  // --- Hero background visuals: converging data streams (skill: §7 animation) ---
  // Bezier paths flow in from both edges toward the centre of the hero, with
  // particles riding along them. Clicking the hero sends out a shockwave that
  // pushes nearby particles off their path.
  (function initHeroFlow() {
    var canvas = document.getElementById('heroFlow');
    if (!canvas || !canvas.getContext) return;

    var hero = document.getElementById('hero');
    var ctx  = canvas.getContext('2d');

    var width = 0, height = 0;
    var paths = [];
    var ripples = [];
    var rafId = null;
    var running = false;

    // Brand-matched stream colours (accent-1 purple → accent-2 blue)
    var LINE_COLOR = 'rgba(140, 124, 255, 0.34)';
    var DOT_INNER  = 'rgba(180, 170, 255, 0.95)';
    var DOT_OUTER  = 'rgba(59, 130, 246, 0.5)';

    function pathCount() {
      // Fewer streams on small screens — keeps paint cost down on mobile.
      if (width < 640) return 26;
      if (width < 1024) return 44;
      return 64;
    }

    function buildPaths() {
      paths = [];
      var count = pathCount();
      for (var i = 0; i < count; i++) {
        paths.push({
          isLeft: i % 2 === 0,
          startY: (i / count) * height * 1.4 - height * 0.2,
          t: Math.random(),
          speed: 0.0014 + Math.random() * 0.0018
        });
      }
    }

    function resize() {
      var rect = hero.getBoundingClientRect();
      var dpr  = Math.min(window.devicePixelRatio || 1, 2);

      width  = Math.max(rect.width, 1);
      height = Math.max(rect.height, 1);

      canvas.width  = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      // setTransform (not scale) — scale would compound on every resize.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      buildPaths();
    }

    function controlPoints(path) {
      var cx = width / 2;
      var cy = height / 2;
      return {
        p0: { x: path.isLeft ? 0 : width,            y: path.startY },
        p1: { x: path.isLeft ? cx * 0.5 : width - cx * 0.5, y: path.startY },
        p2: { x: path.isLeft ? cx * 0.8 : width - cx * 0.8, y: cy },
        p3: { x: cx, y: cy }
      };
    }

    function bezierPoint(t, p0, p1, p2, p3) {
      var u = 1 - t;
      return {
        x: u*u*u * p0.x + 3*u*u*t * p1.x + 3*u*t*t * p2.x + t*t*t * p3.x,
        y: u*u*u * p0.y + 3*u*u*t * p1.y + 3*u*t*t * p2.y + t*t*t * p3.y
      };
    }

    function draw(advance) {
      ctx.clearRect(0, 0, width, height);

      if (advance) {
        for (var r = ripples.length - 1; r >= 0; r--) {
          ripples[r].radius += 14;
          ripples[r].life   -= 0.015;
          if (ripples[r].life <= 0) ripples.splice(r, 1);
        }
      }

      for (var i = 0; i < paths.length; i++) {
        var path = paths[i];
        var cp = controlPoints(path);

        // The stream itself
        ctx.beginPath();
        ctx.moveTo(cp.p0.x, cp.p0.y);
        ctx.bezierCurveTo(cp.p1.x, cp.p1.y, cp.p2.x, cp.p2.y, cp.p3.x, cp.p3.y);
        ctx.strokeStyle = LINE_COLOR;
        ctx.lineWidth = 1.1;
        ctx.setLineDash([2, 6]);
        ctx.stroke();
        ctx.setLineDash([]);

        if (advance) {
          path.t += path.speed;
          if (path.t > 1) {
            path.t = 0;
            // Drift the entry point so the pattern never fully repeats
            path.startY += (Math.random() - 0.5) * 10;
          }
        }

        var pos = bezierPoint(path.t, cp.p0, cp.p1, cp.p2, cp.p3);

        // Shockwave displacement
        for (var e = 0; e < ripples.length; e++) {
          var exp = ripples[e];
          var dx = pos.x - exp.x;
          var dy = pos.y - exp.y;
          var dist = Math.hypot(dx, dy) || 1;
          var offset = Math.abs(dist - exp.radius);
          if (offset < 120) {
            var force = (1 - offset / 120) * exp.life * 80;
            pos.x += (dx / dist) * force;
            pos.y += (dy / dist) * force;
          }
        }

        // Particle: soft halo + bright core
        var fade = Math.sin(path.t * Math.PI); // fade in/out at both ends
        ctx.globalAlpha = fade;
        ctx.fillStyle = DOT_OUTER;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = DOT_INNER;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 1.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    }

    function frame() {
      draw(true);
      rafId = window.requestAnimationFrame(frame);
    }

    function start() {
      if (running || prefersReducedMotion) return;
      running = true;
      rafId = window.requestAnimationFrame(frame);
    }

    function stop() {
      running = false;
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
        rafId = null;
      }
    }

    // Click shockwave — hero only, coordinates relative to the canvas
    hero.addEventListener('click', function (e) {
      if (prefersReducedMotion) return;
      var rect = canvas.getBoundingClientRect();
      ripples.push({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        radius: 0,
        life: 1
      });
    });

    var resizeTimer = null;
    window.addEventListener('resize', function () {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(function () {
        resize();
        if (!running) draw(false);
      }, 150);
    });

    // Don't burn frames while the hero is scrolled away or the tab is hidden
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) {
        entries[0].isIntersecting ? start() : stop();
      }, { threshold: 0 }).observe(hero);
    } else {
      start();
    }

    document.addEventListener('visibilitychange', function () {
      document.hidden ? stop() : start();
    });

    resize();
    // Reduced motion still gets the artwork — just frozen, never animating.
    if (prefersReducedMotion) draw(false);
  })();

  // --- Contact form — inline validation (skill: §8 inline-validation) ---
  var form = document.getElementById('contactForm');
  if (!form) return;

  var formStatus = document.getElementById('formStatus');

  var fields = {
    name:    { el: document.getElementById('name'),    error: document.getElementById('name-error') },
    email:   { el: document.getElementById('email'),   error: document.getElementById('email-error') },
    message: { el: document.getElementById('message'), error: document.getElementById('message-error') }
  };

  // Validate on blur (not on each keystroke — skill: §8 inline-validation)
  Object.values(fields).forEach(function (field) {
    field.el.addEventListener('blur', function () {
      validateField(field);
    });

    // Clear error once user starts typing again
    field.el.addEventListener('input', function () {
      if (field.el.classList.contains('invalid')) {
        field.el.classList.remove('invalid');
        field.error.textContent = '';
      }
    });
  });

  function validateField(field) {
    var el  = field.el;
    var err = field.error;
    var val = el.value.trim();

    if (el.type === 'email') {
      if (!val) {
        setInvalid(el, err, 'Email is required.');
        return false;
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
        setInvalid(el, err, 'Please enter a valid email address.');
        return false;
      }
    } else {
      if (!val) {
        var label = el.closest('.form-group').querySelector('label').textContent.replace('*', '').trim();
        setInvalid(el, err, label + ' is required.');
        return false;
      }
    }

    setValid(el, err);
    return true;
  }

  function setInvalid(el, err, msg) {
    el.classList.add('invalid');
    el.setAttribute('aria-invalid', 'true');
    err.textContent = msg;
  }

  function setValid(el, err) {
    el.classList.remove('invalid');
    el.setAttribute('aria-invalid', 'false');
    err.textContent = '';
  }

  function validateAll() {
    return Object.values(fields).reduce(function (allValid, field) {
      return validateField(field) && allValid;
    }, true);
  }

  function resetFields() {
    form.reset();
    Object.values(fields).forEach(function (field) {
      field.el.classList.remove('invalid');
      field.el.removeAttribute('aria-invalid');
      field.error.textContent = '';
    });
  }

  function showStatus(kind, message) {
    formStatus.className = 'form-status ' + kind;
    formStatus.textContent = message;
    formStatus.scrollIntoView({
      behavior: prefersReducedMotion ? 'auto' : 'smooth',
      block: 'nearest'
    });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();

    formStatus.className = 'form-status';
    formStatus.textContent = '';

    if (!validateAll()) {
      // Focus first invalid field (skill: §8 focus-management)
      var firstInvalid = form.querySelector('.invalid');
      if (firstInvalid) firstInvalid.focus();
      return;
    }

    // Honeypot tripped — silently accept so the bot doesn't retry.
    var honeypot = document.getElementById('botcheck');
    if (honeypot && honeypot.checked) {
      showStatus('success', "Message sent! We'll be in touch within one business day.");
      resetFields();
      return;
    }

    var btn = form.querySelector('button[type="submit"]');
    var originalText = btn.textContent;

    // No key configured yet — don't pretend the message was sent.
    if (!WEB3FORMS_ACCESS_KEY || WEB3FORMS_ACCESS_KEY === 'YOUR-ACCESS-KEY-HERE') {
      showStatus('error',
        'The contact form isn\u2019t connected yet. Please WhatsApp us at ' +
        '+60 12-627 4178 or email ' + CONTACT_EMAIL + ' \u2014 we\u2019ll reply the same day.');
      return;
    }

    btn.textContent = 'Sending\u2026';
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');

    fetch('https://api.web3forms.com/submit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        access_key: WEB3FORMS_ACCESS_KEY,
        subject: 'New enquiry from grndconsulting.com',
        from_name: 'GRND Consulting website',
        name: fields.name.el.value.trim(),
        email: fields.email.el.value.trim(),
        message: fields.message.el.value.trim(),
        // Replies go straight to the person who filled the form in
        replyto: fields.email.el.value.trim()
      })
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.success) {
          throw new Error(result.data && result.data.message || 'Submission failed');
        }
        showStatus('success', "Message sent! We'll be in touch within one business day.");
        resetFields();
      })
      .catch(function () {
        showStatus('error',
          'Something went wrong sending that. Please WhatsApp us at ' +
          '+60 12-627 4178 or email ' + CONTACT_EMAIL + ' instead.');
      })
      .then(function () {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.removeAttribute('aria-busy');
      });
  });

})();
