/**
 * LoanAI — Lightweight Motion & Cursor-Reactive Controller
 * Inspired by Google Antigravity's calm, responsive spatial feel.
 * - Uses requestAnimationFrame with automatic idle sleep (0% CPU when pointer stops).
 * - Respects prefers-reduced-motion and disables pointer tracking on touch/small screens.
 * - Never blocks scrolling, clicking, typing, or text selection.
 */

(function () {
    "use strict";

    const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointerQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
    const desktopWidthQuery = window.matchMedia("(min-width: 769px)");

    function shouldAnimatePointer() {
        return (
            !reducedMotionQuery.matches &&
            finePointerQuery.matches &&
            desktopWidthQuery.matches
        );
    }

    const stage = document.querySelector(".ambient-stage");
    const spotlight = document.getElementById("cursorSpotlight");
    const parallaxLayers = Array.from(document.querySelectorAll("[data-parallax]"));

    let targetX = window.innerWidth * 0.5;
    let targetY = window.innerHeight * 0.35;
    let currentX = targetX;
    let currentY = targetY;
    let rafId = null;
    let isPointerInside = false;

    function updateSpotlightAndParallax() {
        const dx = targetX - currentX;
        const dy = targetY - currentY;

        currentX += dx * 0.11;
        currentY += dy * 0.11;

        if (spotlight) {
            spotlight.style.transform = `translate3d(${currentX}px, ${currentY}px, 0) translate(-50%, -50%)`;
        }

        const centerX = currentX - window.innerWidth * 0.5;
        const centerY = currentY - window.innerHeight * 0.5;

        for (let i = 0; i < parallaxLayers.length; i++) {
            const el = parallaxLayers[i];
            const factor = parseFloat(el.getAttribute("data-parallax")) || 0;
            const px = (centerX * factor).toFixed(2);
            const py = (centerY * factor).toFixed(2);
            el.style.transform = `translate3d(${px}px, ${py}px, 0)`;
        }

        // Sleep the rAF loop once interpolation settles within sub-pixel threshold
        if (Math.abs(dx) > 0.25 || Math.abs(dy) > 0.25) {
            rafId = window.requestAnimationFrame(updateSpotlightAndParallax);
        } else {
            rafId = null;
        }
    }

    function scheduleLoop() {
        if (!rafId && shouldAnimatePointer()) {
            rafId = window.requestAnimationFrame(updateSpotlightAndParallax);
        }
    }

    function resetPointerEffects() {
        if (rafId) {
            window.cancelAnimationFrame(rafId);
            rafId = null;
        }
        if (spotlight) {
            spotlight.style.opacity = "0";
        }
        parallaxLayers.forEach((el) => {
            el.style.transform = "";
        });
    }

    if (stage && spotlight) {
        window.addEventListener(
            "pointermove",
            (e) => {
                if (e.pointerType !== "mouse" || !shouldAnimatePointer()) return;
                targetX = e.clientX;
                targetY = e.clientY;
                if (!isPointerInside) {
                    isPointerInside = true;
                    spotlight.style.opacity = "1";
                }
                scheduleLoop();
            },
            { passive: true }
        );

        document.addEventListener(
            "pointerleave",
            () => {
                isPointerInside = false;
                if (spotlight) spotlight.style.opacity = "0";
            },
            { passive: true }
        );
    }

    // ── Subtle 3D Tilt & Surface Sheen on Interactive Cards ──
    const tiltCards = document.querySelectorAll(".suggestion-card, [data-tilt]");

    tiltCards.forEach((card) => {
        let cardRaf = null;
        let rect = null;
        let lastEvent = null;

        function applyCardTilt() {
            cardRaf = null;
            if (!lastEvent || !rect || !shouldAnimatePointer()) return;

            const relX = (lastEvent.clientX - rect.left) / rect.width;
            const relY = (lastEvent.clientY - rect.top) / rect.height;

            const clampedX = Math.max(0, Math.min(1, relX));
            const clampedY = Math.max(0, Math.min(1, relY));

            const maxTilt = parseFloat(card.getAttribute("data-tilt-max")) || 3.5;
            const rotateY = (clampedX - 0.5) * (maxTilt * 2);
            const rotateX = (0.5 - clampedY) * (maxTilt * 2);

            card.style.setProperty("--card-mx", `${(clampedX * 100).toFixed(1)}%`);
            card.style.setProperty("--card-my", `${(clampedY * 100).toFixed(1)}%`);
            card.style.transform = `perspective(900px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg) translateY(-2px)`;
        }

        card.addEventListener(
            "pointerenter",
            (e) => {
                if (e.pointerType !== "mouse" || !shouldAnimatePointer()) return;
                rect = card.getBoundingClientRect();
                card.classList.add("is-tilting");
            },
            { passive: true }
        );

        card.addEventListener(
            "pointermove",
            (e) => {
                if (e.pointerType !== "mouse" || !shouldAnimatePointer()) return;
                if (!rect) rect = card.getBoundingClientRect();
                lastEvent = e;
                if (!cardRaf) {
                    cardRaf = window.requestAnimationFrame(applyCardTilt);
                }
            },
            { passive: true }
        );

        card.addEventListener(
            "pointerleave",
            () => {
                if (cardRaf) {
                    window.cancelAnimationFrame(cardRaf);
                    cardRaf = null;
                }
                rect = null;
                lastEvent = null;
                card.classList.remove("is-tilting");
                card.style.transform = "";
            },
            { passive: true }
        );
    });

    // React dynamically if user toggles OS reduced-motion or resizes viewport
    function handleEnvChange() {
        if (!shouldAnimatePointer()) {
            resetPointerEffects();
            tiltCards.forEach((card) => {
                card.classList.remove("is-tilting");
                card.style.transform = "";
            });
        }
    }

    if (typeof reducedMotionQuery.addEventListener === "function") {
        reducedMotionQuery.addEventListener("change", handleEnvChange);
        finePointerQuery.addEventListener("change", handleEnvChange);
        desktopWidthQuery.addEventListener("change", handleEnvChange);
    }

    // ── Smooth Theme Toggle Helper (Shared with Form & Chat) ──
    window.LoanAIMotion = {
        triggerThemeTransition: function () {
            if (reducedMotionQuery.matches) return;
            const root = document.documentElement;
            root.classList.add("theme-transitioning");
            window.clearTimeout(root._themeTimer);
            root._themeTimer = window.setTimeout(() => {
                root.classList.remove("theme-transitioning");
            }, 380);
        },
        shouldAnimatePointer: shouldAnimatePointer
    };
})();
