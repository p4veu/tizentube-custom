from pathlib import Path
import sys

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("upstream")

def replace_once(path, old, new, label):
    p = ROOT / path
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")

# Build from the clean upstream TizenTube 1.15.0 source and change only:
# 1) direct Screen Off button placement,
# 2) Screen Off wake-up behavior,
# 3) DIAL/casting target.

custom_ui = ROOT / "mods/ui/customUI.js"
text = custom_ui.read_text(encoding="utf-8")

setting_marker = """        const settingActionGroup = functions.find(func => {
            return func.rhs.includes('TRANSPORT_CONTROLS_BUTTON_TYPE_PLAYBACK_SETTINGS');
        }).left.split('.')[1];"""

screen_command = """        const screenOffCommand = {
            "type": "TRANSPORT_CONTROLS_BUTTON_TYPE_TURN_OFF_SCREEN",
            "button": {
                "buttonRenderer": ButtonRenderer(
                    false,
                    t('player.screenOff'),
                    'EYE_OFF',
                    {
                        customAction: {
                            action: 'SCREEN_OFF',
                        }
                    }
                )
            }
        }

"""
if text.count(setting_marker) != 1:
    raise SystemExit("customUI: playback-settings marker changed upstream")
text = text.replace(setting_marker, screen_command + setting_marker, 1)

# Keep the official Mini Player patch untouched. On this TV its action group
# is not producing the small direct buttons, so Screen Off is injected into
# engagementActions instead (the same group used by TizenTube's speed button).
# Insert our wrapper LAST so it wraps all upstream engagement-action filters.
prev_next_marker = """        if (configRead('enablePreviousNextButtons')) {"""

screen_wrapper = """        if (engagementActionButton) {
            const origScreenOffActionButton = inst[engagementActionButton];
            if (typeof origScreenOffActionButton === 'function') {
                inst[engagementActionButton] = function () {
                    const res = origScreenOffActionButton.apply(this, arguments);
                    if (!Array.isArray(res)) return res;

                    if (!res.find(item => item.type === 'TRANSPORT_CONTROLS_BUTTON_TYPE_TURN_OFF_SCREEN')) {
                        // Put it first so older/limited Leanback layouts do not
                        // push it out when only a few small buttons are visible.
                        res.unshift(screenOffCommand);
                    }

                    return res;
                };
            }
        }

"""
if text.count(prev_next_marker) != 1:
    raise SystemExit("customUI: previous/next marker changed upstream")
text = text.replace(prev_next_marker, screen_wrapper + prev_next_marker, 1)
custom_ui.write_text(text, encoding="utf-8")

# Replace upstream SCREEN_OFF implementation. Upstream hides every body child
# and ui.js later restores every one with display:block, which can expose the
# normally hidden Theme Configuration panel.
replace_once(
    "mods/resolveCommand.js",
    "import checkForUpdates from './features/updater.js';",
    "import checkForUpdates from './features/updater.js';\nimport { turnOffScreen } from './features/turnOffScreen.js';",
    "resolveCommand import"
)

old_screen = """        case 'SCREEN_OFF':
            for (const child of document.body.children) {
                if (child.tagName.toLowerCase() === 'script' || child.tagName.toLowerCase() === 'svg') continue;
                child.style.setProperty('display', 'none', 'important');
            }
            window.screenTurnedOffAt = Date.now();
            break;"""
new_screen = """        case 'SCREEN_OFF':
            turnOffScreen();
            break;"""
replace_once("mods/resolveCommand.js", old_screen, new_screen, "SCREEN_OFF implementation")

turn_off = r"""let cleanupWakeGuard = null;

function swallow(event) {
    try { event.preventDefault(); } catch (_) {}
    try { event.stopPropagation(); } catch (_) {}
    try {
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    } catch (_) {}
}

function removeOverlay() {
    const overlay = document.getElementById('__ttcc_screen_off_overlay');
    if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
    }
}

export function turnOffScreen() {
    if (cleanupWakeGuard) {
        cleanupWakeGuard();
        cleanupWakeGuard = null;
    }

    removeOverlay();

    // Never use TizenTube's stock screenTurnedOffAt wake path. Its ui.js
    // restores every body child with display:block and can show Theme Config.
    window.screenTurnedOffAt = null;

    const overlay = document.createElement('div');
    overlay.id = '__ttcc_screen_off_overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.style.setProperty('position', 'fixed', 'important');
    overlay.style.setProperty('left', '0', 'important');
    overlay.style.setProperty('top', '0', 'important');
    overlay.style.setProperty('right', '0', 'important');
    overlay.style.setProperty('bottom', '0', 'important');
    overlay.style.setProperty('width', '100vw', 'important');
    overlay.style.setProperty('height', '100vh', 'important');
    overlay.style.setProperty('margin', '0', 'important');
    overlay.style.setProperty('padding', '0', 'important');
    overlay.style.setProperty('background', '#000', 'important');
    overlay.style.setProperty('z-index', '2147483647', 'important');
    overlay.style.setProperty('pointer-events', 'none', 'important');
    (document.body || document.documentElement).appendChild(overlay);

    let waking = false;
    let wakeKeyCode = 0;
    let fallbackTimer = null;
    const types = ['keydown', 'keypress', 'keyup'];

    // SCREEN_OFF is normally invoked by pressing OK. The keyup from THAT SAME
    // press arrives after the overlay is created. v1 treated it as a wake key,
    // so the picture came back immediately. Swallow the tail of the activation
    // key for a short grace period, then arm normal wake-up.
    const armAt = Date.now() + 600;

    const cleanup = () => {
        for (const type of types) {
            window.removeEventListener(type, wakeGuard, true);
        }
        if (fallbackTimer) {
            clearTimeout(fallbackTimer);
            fallbackTimer = null;
        }
        if (cleanupWakeGuard === cleanup) cleanupWakeGuard = null;
    };

    const wakeGuard = (event) => {
        // Window capture runs before TizenTube's document-capture handlers.
        const code = event.keyCode || event.which || 0;

        // TTCC v3: Play/Pause controls playback WITHOUT waking the picture.
        // Samsung Smart Remote: MediaPlayPause = 10252.
        // Also allow separate MediaPlay (415) and MediaPause (19) keys.
        // Do not swallow these events: YouTube must receive them normally.
        if (code === 10252 || code === 415 || code === 19) {
            return true;
        }

        // Every other key belongs to the Screen Off wake sequence.
        swallow(event);

        if (Date.now() < armAt) {
            return false;
        }

        if (!waking) {
            waking = true;
            wakeKeyCode = code;
            removeOverlay();

            // Fallback for Samsung firmware/remotes that do not emit keyup.
            fallbackTimer = setTimeout(cleanup, 900);
        }

        if (event.type === 'keyup' && (!wakeKeyCode || !code || code === wakeKeyCode)) {
            cleanup();
        }

        return false;
    };

    cleanupWakeGuard = cleanup;
    for (const type of types) {
        window.addEventListener(type, wakeGuard, true);
    }
}
"""
(ROOT / "mods/features/turnOffScreen.js").write_text(turn_off, encoding="utf-8")

# Polish label used by both the existing More settings item and direct button.
pl = ROOT / "mods/translations/resources/pl.json"
pl_text = pl.read_text(encoding="utf-8")
if '"screenOff": "Turn off screen"' in pl_text:
    pl.write_text(pl_text.replace('"screenOff": "Turn off screen"', '"screenOff": "Wyłącz ekran"', 1), encoding="utf-8")

# Casting/DIAL must reopen this GitHub module, not the upstream npm module.
replace_once(
    "service/service.js",
    "moduleName: '@foxreis/tizentube',",
    "moduleName: 'p4veu/ttcc',",
    "DIAL module name"
)
replace_once(
    "service/service.js",
    "moduleType: 'npm',",
    "moduleType: 'gh',",
    "DIAL module type"
)

print("TTCC v3 patch applied successfully")
