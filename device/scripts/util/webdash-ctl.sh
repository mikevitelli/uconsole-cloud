#!/bin/bash
# Webdash service control for TUI
case "${1:-}" in
    start)
        sudo systemctl start uconsole-webdash && echo "Webdash started." || echo "Failed to start."
        ;;
    stop)
        sudo systemctl stop uconsole-webdash && echo "Webdash stopped." || echo "Failed to stop."
        ;;
    restart)
        sudo systemctl restart uconsole-webdash && echo "Webdash restarted." || echo "Failed to restart."
        ;;
    logs)
        journalctl -u uconsole-webdash --no-pager -n 50 2>/dev/null || echo "No logs available."
        ;;
    config)
        echo ""
        echo "  Change webdash password:"
        echo ""
        /opt/uconsole/bin/uconsole-passwd
        echo ""
        read -rp "  Restart webdash now? [Y/n]: " RESTART
        [ "$RESTART" = "b" ] && exit 0
        if [ "${RESTART,,}" != "n" ]; then
            sudo systemctl restart uconsole-webdash && echo "  Webdash restarted." || echo "  Failed to restart."
        fi
        ;;
    *)
        echo "Usage: webdash-ctl.sh {start|stop|restart|logs|config}"
        exit 1
        ;;
esac
