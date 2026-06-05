/* ============================================
   GRND Consulting — Interactions
   ui-ux-pro-max: §1 accessibility, §2 interaction,
                  §7 animation, §8 forms
   ============================================ */

(function () {
  'use strict';

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

  form.addEventListener('submit', function (e) {
    e.preventDefault();

    // Clear status
    formStatus.className = 'form-status';
    formStatus.textContent = '';

    if (!validateAll()) {
      // Focus first invalid field (skill: §8 focus-management)
      var firstInvalid = form.querySelector('.invalid');
      if (firstInvalid) firstInvalid.focus();
      return;
    }

    var btn = form.querySelector('button[type="submit"]');
    var originalText = btn.textContent;
    btn.textContent = 'Sending…';
    btn.disabled = true;

    // Simulate async submit — replace with real endpoint when ready
    setTimeout(function () {
      btn.textContent = originalText;
      btn.disabled = false;

      formStatus.className = 'form-status success';
      formStatus.textContent = "Message sent! We'll be in touch within one business day.";
      formStatus.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'nearest' });

      form.reset();
      Object.values(fields).forEach(function (field) {
        field.el.classList.remove('invalid');
        field.el.removeAttribute('aria-invalid');
        field.error.textContent = '';
      });
    }, 1200);
  });

})();
