#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
hypr_control.sh — lightweight Hyprland dispatcher helper

Usage:
  hypr_control.sh [options]

Options:
  --workspace <id>        Switch focus to the given workspace ID (numeric or named).
  --fullscreen <mode>     Set fullscreen state for the focused window. Mode must be
                          one of: enable, disable, toggle.
  --monitor <name|index>  Focus the target monitor (e.g. DP-1 or 0).
  --move-window <id>      Move the focused window to the target workspace.
  --print-signature       Output the Hyprland instance signature and exit.
  --help                  Show this help message.

Multiple options may be combined; they are executed in the order provided.

Examples:
  hypr_control.sh --workspace 3 --fullscreen toggle
  hypr_control.sh --monitor DP-1 --workspace 1
  hypr_control.sh --print-signature

EOF
}

error() {
    echo "[hypr_control] $1" >&2
    exit 1
}

ensure_hyprctl() {
    command -v hyprctl >/dev/null 2>&1 || error "hyprctl not found in PATH"
}

resolve_signature() {
    local runtime_dir signature_dir
    runtime_dir=${XDG_RUNTIME_DIR:-""}
    signature_dir="${runtime_dir}/hypr"

    if [[ -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
        echo "$HYPRLAND_INSTANCE_SIGNATURE"
        return
    fi

    if [[ -z $runtime_dir || ! -d $signature_dir ]]; then
        error "Unable to locate Hyprland runtime directory. Ensure Hyprland is running."
    fi

    local first_signature
    first_signature=$(ls "$signature_dir" 2>/dev/null | head -n1 || true)
    if [[ -z $first_signature ]]; then
        error "No Hyprland instance signatures found in $signature_dir"
    fi

    echo "$first_signature"
}

dispatch_workspace() {
    local target=$1
    echo "Switching to workspace ${target}"
    hyprctl dispatch workspace "$target"
}

dispatch_fullscreen() {
    local mode=$1
    case "$mode" in
        enable|disable|toggle)
            echo "Setting fullscreen: ${mode}"
            hyprctl dispatch fullscreen "$mode"
            ;;
        *)
            error "Invalid fullscreen mode '$mode'. Use enable, disable, or toggle."
            ;;
    esac
}

dispatch_monitor() {
    local monitor=$1
    echo "Focusing monitor ${monitor}"
    hyprctl dispatch focusmonitor "$monitor"
}

dispatch_move_window() {
    local workspace=$1
    echo "Moving focused window to workspace ${workspace}"
    hyprctl dispatch movetoworkspace "$workspace"
}

main() {
    local actions=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --workspace)
                [[ $# -ge 2 ]] || error "--workspace requires a value"
                actions+=("workspace" "$2")
                shift 2
                ;;
            --fullscreen)
                [[ $# -ge 2 ]] || error "--fullscreen requires a mode"
                actions+=("fullscreen" "$2")
                shift 2
                ;;
            --monitor)
                [[ $# -ge 2 ]] || error "--monitor requires a name or index"
                actions+=("monitor" "$2")
                shift 2
                ;;
            --move-window)
                [[ $# -ge 2 ]] || error "--move-window requires a workspace"
                actions+=("move_window" "$2")
                shift 2
                ;;
            --print-signature)
                actions+=("print_signature")
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            --)
                shift
                break
                ;;
            *)
                error "Unknown option '$1'. Use --help for usage."
                ;;
        esac
    done

    ensure_hyprctl

    local signature
    signature=$(resolve_signature)
    export HYPRLAND_INSTANCE_SIGNATURE="$signature"

    if [[ ${#actions[@]} -eq 0 ]]; then
        echo "HYPRLAND_INSTANCE_SIGNATURE=${signature}"
        echo "No actions requested. Use --help for available options."
        exit 0
    fi

    local i=0
    while [[ $i -lt ${#actions[@]} ]]; do
        local action=${actions[$i]}
        case "$action" in
            workspace)
                dispatch_workspace "${actions[$((i + 1))]}"
                ((i+=2))
                ;;
            fullscreen)
                dispatch_fullscreen "${actions[$((i + 1))]}"
                ((i+=2))
                ;;
            monitor)
                dispatch_monitor "${actions[$((i + 1))]}"
                ((i+=2))
                ;;
            move_window)
                dispatch_move_window "${actions[$((i + 1))]}"
                ((i+=2))
                ;;
            print_signature)
                echo "HYPRLAND_INSTANCE_SIGNATURE=${signature}"
                ((i+=1))
                ;;
            *)
                error "Unhandled action '$action'"
                ;;
        esac
    done
}

main "$@"