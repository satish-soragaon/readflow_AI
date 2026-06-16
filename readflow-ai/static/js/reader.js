/**
 * ReadFlow AI — RSVP reader engine.
 *
 * Responsibilities:
 *   - RSVP playback: word / chunk / sentence / line modes with smart pauses.
 *   - Progress persistence via periodic fetch to /api/reader/progress.
 *   - Annotation creation via fetch (no full-page reload).
 *   - Annotation deletion via DELETE fetch.
 *   - Live "time remaining" estimate.
 *   - Keyboard shortcuts: Space (pause/resume), ← (back), → (forward), R (restart).
 */
(function () {
    "use strict";

    // ── Constants ──────────────────────────────────────────────────────────
    const WPM_OPTIONS = [100, 200, 300, 450, 600, 800, 1000];

    // Read CSRF token once; included in every state-changing fetch request.
    const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content ?? "";

    // Text and config injected by the template
    const text   = window.READFLOW_TEXT   || "";
    const config = window.READFLOW_CONFIG || {};
    const words  = text.match(/\S+/g) || [];

    // ── DOM refs ───────────────────────────────────────────────────────────
    const wordDisplay    = document.getElementById("word-display");
    const wpmSlider      = document.getElementById("wpm-slider");
    const wpmValue       = document.getElementById("wpm-value");
    const readingMode    = document.getElementById("reading-mode");
    const currentWordEl  = document.getElementById("current-word");
    const totalWordsEl   = document.getElementById("total-words");
    const completionEl   = document.getElementById("completion");
    const progressFill   = document.getElementById("progress-fill");
    const timeRemaining  = document.getElementById("time-remaining");

    // Hidden position inputs that are kept in sync for annotation forms
    const positionInputs = [
        document.getElementById("bookmark-position"),
        document.getElementById("note-position"),
        document.getElementById("highlight-position"),
    ].filter(Boolean);

    // ── State ──────────────────────────────────────────────────────────────
    let currentIndex = 0;
    let timerId      = null;
    let isRunning    = false;
    let startedAt    = Date.now();
    let lastSavedAt  = 0;
    let segments     = buildSegments(config.defaultMode || "word");

    // ── Initialise ─────────────────────────────────────────────────────────
    function init() {
        const wpmIndex = WPM_OPTIONS.indexOf(Number(config.defaultWpm || 200));
        wpmSlider.value   = String(wpmIndex === -1 ? 1 : wpmIndex);
        readingMode.value = config.defaultMode || "word";
        segments          = buildSegments(readingMode.value);
        currentIndex      = findSegmentIndex(Number(config.startPosition || 0));
        if (wordDisplay) wordDisplay.dataset.mode = readingMode.value;
        updateWpmLabel();
        updateProgress();
        if (currentIndex >= segments.length && segments.length > 0) {
            wordDisplay.textContent = "Done — press Start to read again";
        }
    }

    // ── Timing ─────────────────────────────────────────────────────────────
    function getBaseInterval() {
        // 80ms floor keeps words perceptible even at maximum WPM (1000 → 60ms → clamped to 80)
        return Math.max(80, 60_000 / WPM_OPTIONS[Number(wpmSlider.value)]);
    }

    function getDelay(segment) {
        if (!config.smartPauseEnabled) return getBaseInterval();
        const val         = segment.text.trim();
        const segWords    = val.match(/\S+/g) || [];
        let multiplier    = 1;
        if (/[,;:]$/.test(val))  multiplier = Math.max(multiplier, 2);
        if (/[.!?]$/.test(val))  multiplier = Math.max(multiplier, 3);
        if (segWords.some(w => cleanWord(w).length > 12)) multiplier = Math.max(multiplier, 2);
        else if (segWords.some(w => cleanWord(w).length > 8)) multiplier = Math.max(multiplier, 1.5);
        return getBaseInterval() * multiplier;
    }

    // ── Text helpers ────────────────────────────────────────────────────────
    function cleanWord(v) { return v.replace(/[^\p{L}\p{N}]/gu, ""); }

    function escapeHtml(v) {
        return v.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
                .replace(/"/g,"&quot;").replace(/'/g,"&#039;");
    }

    function withFocusLetter(word) {
        if (!word) return "";
        const letters    = Array.from(word);
        const focusIndex = Math.floor(letters.length / 2);
        return letters.map((l, i) =>
            i === focusIndex
                ? `<span class="focus-letter">${escapeHtml(l)}</span>`
                : escapeHtml(l)
        ).join("");
    }

    function withFocusLetters(value) {
        return value.split(/(\s+)/).map(part =>
            part.trim() ? withFocusLetter(part) : part
        ).join("");
    }

    // ── Segments ────────────────────────────────────────────────────────────
    function makeSegment(textValue, startWord, wordCount) {
        return { text: textValue, startWord, endWord: startWord + wordCount };
    }

    function buildSegments(mode) {
        if (mode === "sentence") {
            return buildTextSegments(
                (text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || []).map(s => s.trim()).filter(Boolean)
            );
        }
        if (mode === "line") {
            return buildTextSegments(
                text.split(/\n+/).map(l => l.trim()).filter(Boolean)
            );
        }
        if (mode === "chunk") {
            const out = [];
            for (let i = 0; i < words.length; i += 4) {
                const chunk = words.slice(i, i + 4);
                out.push(makeSegment(chunk.join(" "), i, chunk.length));
            }
            return out;
        }
        return words.map((w, i) => makeSegment(w, i, 1));
    }

    function buildTextSegments(items) {
        let startWord = 0;
        return items.map(item => {
            const count   = (item.match(/\S+/g) || []).length;
            const segment = makeSegment(item, startWord, count);
            startWord += count;
            return segment;
        });
    }

    function findSegmentIndex(position) {
        const idx = segments.findIndex(seg => seg.endWord > position);
        return idx === -1 ? segments.length : idx;
    }

    // ── Progress ────────────────────────────────────────────────────────────
    function getDisplayedCount() {
        // When currentIndex === 0, nothing has been shown yet
        if (currentIndex === 0) return Number(config.startPosition || 0);
        const seg = segments[currentIndex - 1];
        return seg ? Math.min(seg.endWord, words.length) : 0;
    }

    function getPercent(count) {
        return words.length === 0 ? 0 : Math.round((count / words.length) * 100);
    }

    function formatTime(seconds) {
        if (!isFinite(seconds) || seconds < 0) return "--";
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
        return m > 0 ? `${m}m ${s}s` : `${s}s`;
    }

    function updateProgress() {
        const count   = Math.min(getDisplayedCount(), words.length);
        const percent = getPercent(count);

        if (currentWordEl) currentWordEl.textContent  = String(count);
        if (completionEl)  completionEl.textContent   = `${percent}%`;
        if (progressFill) {
            progressFill.style.width = `${percent}%`;
            progressFill.parentElement?.setAttribute("aria-valuenow", percent);
        }

        // Time remaining estimate
        if (timeRemaining) {
            const remaining = words.length - count;
            const wpm       = WPM_OPTIONS[Number(wpmSlider.value)];
            timeRemaining.textContent = wpm > 0 ? formatTime((remaining / wpm) * 60) : "--";
        }

        // Keep annotation form position inputs in sync
        positionInputs.forEach(input => { input.value = String(count); });
    }

    function updateWpmLabel() {
        if (wpmValue) wpmValue.textContent = `${WPM_OPTIONS[Number(wpmSlider.value)]} WPM`;
    }

    // ── Playback ────────────────────────────────────────────────────────────
    function stopTimer() {
        if (timerId) { clearTimeout(timerId); timerId = null; }
    }

    function showSegment() {
        if (currentIndex >= segments.length) {
            isRunning = false;
            stopTimer();
            wordDisplay.textContent = "Done — press Start to read again";
            updateProgress();
            saveProgress(true);
            return;
        }
        const segment          = segments[currentIndex];
        wordDisplay.innerHTML  = readingMode.value === "word"
            ? withFocusLetters(segment.text)
            : escapeHtml(segment.text);
        currentIndex += 1;
        updateProgress();
        saveProgress(false);
        if (isRunning) timerId = setTimeout(showSegment, getDelay(segment));
    }

    function startReading(reset) {
        if (!segments.length) { wordDisplay.textContent = "No text"; return; }
        stopTimer();
        // Always reset on explicit Start; also restart if already at end (finished read)
        if (reset || currentIndex >= segments.length) {
            currentIndex = 0;
            startedAt = Date.now();
        }
        isRunning = true;
        showSegment();
    }

    function pauseReading() {
        isRunning = false;
        stopTimer();
        saveProgress(true);
    }

    function togglePauseResume() {
        if (isRunning) pauseReading(); else startReading(false);
    }

    function movePrevious() {
        pauseReading();
        currentIndex = Math.max(0, currentIndex - 2);
        showSegment();
    }

    function moveNext() {
        pauseReading();
        showSegment();
    }

    function restartReading() {
        currentIndex  = 0;
        startedAt     = Date.now();
        wordDisplay.textContent = "Ready";
        updateProgress();
        saveProgress(true);
        startReading(true);
    }

    function rebuildForMode() {
        const consumed = getDisplayedCount();
        segments       = buildSegments(readingMode.value);
        currentIndex   = findSegmentIndex(consumed);
        if (wordDisplay) wordDisplay.dataset.mode = readingMode.value;
        if (isRunning) { stopTimer(); showSegment(); }
        else { updateProgress(); saveProgress(true); }
    }

    // ── Progress persistence ────────────────────────────────────────────────
    function saveProgress(force) {
        const now = Date.now();
        if (!force && now - lastSavedAt < 5_000) return;
        lastSavedAt = now;

        const count = Math.min(getDisplayedCount(), words.length);
        fetch("/api/reader/progress", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": CSRF_TOKEN,
            },
            keepalive: true,
            body: JSON.stringify({
                document_id:      config.documentId,
                session_id:       config.sessionId,
                position:         count,
                wpm:              WPM_OPTIONS[Number(wpmSlider.value)],
                mode:             readingMode.value,
                completion:       getPercent(count),
                duration_seconds: Math.max(0, Math.round((now - startedAt) / 1000)),
            }),
        }).catch(() => {});
    }

    // ── Annotation submission via fetch ─────────────────────────────────────
    /**
     * Intercepts annotation form submits so the reader does not reload.
     * On success, prepends the new item to the matching companion card list.
     */
    function initAnnotationForms() {
        document.querySelectorAll(".annotation-form").forEach(form => {
            form.addEventListener("submit", async event => {
                event.preventDefault();

                // Sync position to current reader state before sending
                const pos = form.querySelector("[name='position']");
                if (pos) pos.value = String(getDisplayedCount());

                const data  = Object.fromEntries(new FormData(form));
                const input = form.querySelector("input[type='text']");

                try {
                    const resp = await fetch(form.action, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRFToken": CSRF_TOKEN,
                        },
                        body: JSON.stringify(data),
                    });
                    const json = await resp.json();
                    if (json.ok) {
                        _prependAnnotation(form.dataset.type, json.item);
                        if (input) input.value = "";
                    }
                } catch (err) {
                    console.error("Annotation save failed:", err);
                }
            });
        });
    }

    function _prependAnnotation(type, item) {
        const listId = `${type}s-list`;
        const list   = document.getElementById(listId);
        const emptyId = `${type}s-empty`;
        const empty  = document.getElementById(emptyId);
        if (!list) return;

        if (empty) empty.remove();

        const wrapper = document.createElement("div");
        wrapper.className = "annotation-item";
        wrapper.dataset.id = item.id;

        let inner = "";
        if (type === "bookmark") {
            inner = `<button class="jump-button" data-position="${item.position}" type="button">
                        ${_esc(item.label)} · word ${item.position}
                     </button>`;
        } else {
            inner = `<p class="annotation-body">
                        <strong>Word ${item.position}</strong><br>${_esc(item.body ?? item.text ?? "")}
                     </p>`;
        }

        // Build the delete URL from the config (server-side URL pattern)
        const deleteUrl = _buildDeleteUrl(type, item.id);
        wrapper.innerHTML = `${inner}
            <button class="delete-annotation icon-btn"
                    data-url="${deleteUrl}"
                    title="Delete ${type}" aria-label="Delete ${type}">&#10005;</button>`;

        list.prepend(wrapper);

        // Re-wire jump if it's a bookmark
        wrapper.querySelector(".jump-button")?.addEventListener("click", evt => {
            pauseReading();
            currentIndex = findSegmentIndex(Number(evt.currentTarget.dataset.position || 0));
            showSegment();
        });
    }

    function _buildDeleteUrl(type, id) {
        // Config exposes addBookmarkUrl etc.; derive delete URL from it
        const base = config[`add${type.charAt(0).toUpperCase() + type.slice(1)}Url`] || "";
        return base ? `${base}/${id}` : "#";
    }

    function _esc(str) {
        return String(str)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;")
            .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    }

    // ── Annotation deletion ─────────────────────────────────────────────────
    function initDeleteButtons() {
        // Delegate to the companion section so newly added items also work
        document.querySelector(".reader-companion")?.addEventListener("click", async event => {
            const btn = event.target.closest(".delete-annotation");
            if (!btn) return;

            const url  = btn.dataset.url;
            const item = btn.closest(".annotation-item");
            const list = item?.parentElement;
            if (!url || url === "#") return;

            try {
                const resp = await fetch(url, {
                    method: "DELETE",
                    headers: { "X-CSRFToken": CSRF_TOKEN },
                });
                const json = await resp.json();
                if (json.ok && item) {
                    item.remove();
                    // Show empty state if list is now empty
                    if (list && !list.querySelector(".annotation-item")) {
                        const card   = list.closest(".card");
                        const type   = (card?.id?.replace("-card", "") ?? "") + "s";
                        const p      = document.createElement("p");
                        p.className  = "empty-state";
                        p.textContent = `No ${type} yet.`;
                        list.appendChild(p);
                    }
                }
            } catch (err) {
                console.error("Delete annotation failed:", err);
            }
        });
    }

    // ── Event wiring ────────────────────────────────────────────────────────
    document.getElementById("start-button")?.addEventListener("click",   () => startReading(true));
    document.getElementById("pause-button")?.addEventListener("click",   pauseReading);
    document.getElementById("resume-button")?.addEventListener("click",  () => startReading(false));
    document.getElementById("previous-button")?.addEventListener("click", movePrevious);
    document.getElementById("next-button")?.addEventListener("click",    moveNext);
    document.getElementById("restart-button")?.addEventListener("click", restartReading);

    readingMode?.addEventListener("change", rebuildForMode);

    wpmSlider?.addEventListener("input", () => {
        updateWpmLabel();
        updateProgress();
        saveProgress(true);
        if (isRunning) { stopTimer(); timerId = setTimeout(showSegment, getBaseInterval()); }
    });

    // Existing jump buttons rendered by the server
    document.querySelectorAll(".jump-button").forEach(btn => {
        btn.addEventListener("click", () => {
            pauseReading();
            currentIndex = findSegmentIndex(Number(btn.dataset.position || 0));
            showSegment();
        });
    });

    document.addEventListener("keydown", event => {
        if (event.target.matches("input, textarea, select")) return;
        switch (event.code) {
            case "Space":       event.preventDefault(); togglePauseResume(); break;
            case "ArrowLeft":   event.preventDefault(); movePrevious();      break;
            case "ArrowRight":  event.preventDefault(); moveNext();          break;
            default:
                if (event.key.toLowerCase() === "r") { event.preventDefault(); restartReading(); }
        }
    });

    window.addEventListener("beforeunload", () => saveProgress(true));

    // ── Boot ────────────────────────────────────────────────────────────────
    init();
    initAnnotationForms();
    initDeleteButtons();
})();
