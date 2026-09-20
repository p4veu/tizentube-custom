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

# 1) Direct player-bar "Turn off screen" button.
# We keep upstream Mini Player logic intact and add Screen Off at the FRONT of
# the same player-actions group. This maximizes the chance it remains visible
# on older/limited Leanback layouts where later buttons may be omitted.
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

old_wrapper = """        const origSettingActionGroup = inst[settingActionGroup];
        if (configRead('enableMPButton')) {
            inst[settingActionGroup] = function () {
                const res = origSettingActionGroup.apply(this, arguments);
                const idx = res.findIndex(item => item.type === 'TRANSPORT_CONTROLS_BUTTON_TYPE_PLAYBACK_SETTINGS');
                res.find(item => item.type === 'TRANSPORT_CONTROLS_BUTTON_TYPE_PIP') || res.splice(idx, 0, pipCommand);
                return res;
            };
        }"""

new_wrapper = """        const origSettingActionGroup = inst[settingActionGroup];
        if (typeof origSettingActionGroup === 'function') {
            inst[settingActionGroup] = function () {
                const res = origSettingActionGroup.apply(this, arguments);
                if (!Array.isArray(res)) return res;

                // Put Screen Off first so it is not pushed out by the limited
                // number of player buttons on older Samsung / Leanback builds.
                if (!res.find(item => item.type === 'TRANSPORT_CONTROLS_BUTTON_TYPE_TURN_OFF_SCREEN')) {
                    res.unshift(screenOffCommand);
                }

                // Preserve the official TizenTube Mini Player behavior.
                if (configRead('enableMPButton') && !res.find(item => item.type === 'TRANSPORT_CONTROLS_BUTTON_TYPE_PIP')) {
                    const idx = res.findIndex(item => item.type === 'TRANSPORT_CONTROLS_BUTTON_TYPE_PLAYBACK_SETTINGS');
                    res.splice(idx >= 0 ? idx : res.length, 0, pipCommand);
                }

                return res;
            };
        }"""
if text.count(old_wrapper) != 1:
    raise SystemExit("customUI: official settings wrapper changed upstream")
text = text.replace(old_wrapper, new_wrapper, 1)
custom_ui.write_text(text, encoding="utf-8")

# 2) Replace upstream SCREEN_OFF implementation. The official 1.15.0 code
# sets every body child to display:none and the wake handler later forces them
# all to display:block. That is what can expose the hidden Theme Configuration.
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
    // Clean up any stale guard from a previous invocation.
    if (cleanupWakeGuard) {
        cleanupWakeGuard();
        cleanupWakeGuard = null;
    }

    removeOverlay();

    // IMPORTANT: do not set window.screenTurnedOffAt.
    // TizenTube's stock ui.js watches that variable and, on wake, forces every
    // body child to display:block. That can make Theme Configuration visible.
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
        // Window capture runs before TizenTube's document capture handler.
        // Swallow the WHOLE first key sequence so the wake-up button cannot
        // also open Theme Configuration (red / keyCode 403) or trigger YouTube.
        swallow(event);

        const code = event.keyCode || event.which || 0;

        if (!waking) {
            waking = true;
            wakeKeyCode = code;
            removeOverlay();

            // Some Samsung firmware/remotes may omit keyup.
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
p = ROOT / "mods/features/turnOffScreen.js"
p.write_text(turn_off, encoding="utf-8")

# Polish label for the existing playback-settings item and our direct button.
pl = ROOT / "mods/translations/resources/pl.json"
pl_text = pl.read_text(encoding="utf-8")
if '"screenOff": "Turn off screen"' in pl_text:
    pl.write_text(pl_text.replace('"screenOff": "Turn off screen"', '"screenOff": "Wyłącz ekran"', 1), encoding="utf-8")

# 3) Casting/DIAL must launch THIS GitHub module rather than the upstream npm
# module, otherwise casting would silently jump back to official TizenTube.
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

print("TTCC patch applied successfully")
