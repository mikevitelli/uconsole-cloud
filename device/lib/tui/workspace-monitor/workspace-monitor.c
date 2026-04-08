#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include "ext-workspace-v1-client.h"

#define MAX_WS 16

static struct ext_workspace_manager_v1 *ws_manager = NULL;

static struct {
    struct ext_workspace_handle_v1 *handle;
    char name[64];
    int index;       /* order of creation */
    uint32_t state;  /* bitmask: 1=active */
} workspaces[MAX_WS];
static int ws_count = 0;

static char output_path[256];
static char tmp_path[260];
static volatile int running = 1;

static void write_active(void) {
    for (int i = 0; i < ws_count; i++) {
        if (workspaces[i].state & EXT_WORKSPACE_HANDLE_V1_STATE_ACTIVE) {
            FILE *f = fopen(tmp_path, "w");
            if (f) {
                fprintf(f, "%s\n", workspaces[i].name);
                fclose(f);
                rename(tmp_path, output_path);
            }
            return;
        }
    }
}

/* ── workspace handle listener ─────────────────────────────────── */

static void ws_id(void *data, struct ext_workspace_handle_v1 *h, const char *id) {
    (void)data; (void)h; (void)id;
}

static void ws_name(void *data, struct ext_workspace_handle_v1 *h, const char *name) {
    (void)data;
    for (int i = 0; i < ws_count; i++) {
        if (workspaces[i].handle == h) {
            snprintf(workspaces[i].name, sizeof(workspaces[i].name), "%s", name);
            return;
        }
    }
}

static void ws_coordinates(void *data, struct ext_workspace_handle_v1 *h,
                           struct wl_array *coords) {
    (void)data; (void)h; (void)coords;
}

static void ws_state(void *data, struct ext_workspace_handle_v1 *h, uint32_t state) {
    (void)data;
    for (int i = 0; i < ws_count; i++) {
        if (workspaces[i].handle == h) {
            workspaces[i].state = state;
            return;
        }
    }
}

static void ws_capabilities(void *data, struct ext_workspace_handle_v1 *h,
                            uint32_t caps) {
    (void)data; (void)h; (void)caps;
}

static void ws_removed(void *data, struct ext_workspace_handle_v1 *h) {
    (void)data;
    for (int i = 0; i < ws_count; i++) {
        if (workspaces[i].handle == h) {
            ext_workspace_handle_v1_destroy(h);
            for (int j = i; j < ws_count - 1; j++)
                workspaces[j] = workspaces[j + 1];
            ws_count--;
            return;
        }
    }
}

static const struct ext_workspace_handle_v1_listener ws_handle_listener = {
    .id = ws_id,
    .name = ws_name,
    .coordinates = ws_coordinates,
    .state = ws_state,
    .capabilities = ws_capabilities,
    .removed = ws_removed,
};

/* ── group handle listener ─────────────────────────────────────── */

static void group_capabilities(void *data, struct ext_workspace_group_handle_v1 *g,
                               uint32_t caps) {
    (void)data; (void)g; (void)caps;
}

static void group_output_enter(void *data, struct ext_workspace_group_handle_v1 *g,
                               struct wl_output *output) {
    (void)data; (void)g; (void)output;
}

static void group_output_leave(void *data, struct ext_workspace_group_handle_v1 *g,
                               struct wl_output *output) {
    (void)data; (void)g; (void)output;
}

static void group_workspace_enter(void *data, struct ext_workspace_group_handle_v1 *g,
                                  struct ext_workspace_handle_v1 *ws) {
    (void)data; (void)g; (void)ws;
}

static void group_workspace_leave(void *data, struct ext_workspace_group_handle_v1 *g,
                                  struct ext_workspace_handle_v1 *ws) {
    (void)data; (void)g; (void)ws;
}

static void group_removed(void *data, struct ext_workspace_group_handle_v1 *g) {
    (void)data; (void)g;
}

static const struct ext_workspace_group_handle_v1_listener group_listener = {
    .capabilities = group_capabilities,
    .output_enter = group_output_enter,
    .output_leave = group_output_leave,
    .workspace_enter = group_workspace_enter,
    .workspace_leave = group_workspace_leave,
    .removed = group_removed,
};

/* ── manager listener ──────────────────────────────────────────── */

static void mgr_workspace_group(void *data, struct ext_workspace_manager_v1 *m,
                                struct ext_workspace_group_handle_v1 *group) {
    (void)data; (void)m;
    ext_workspace_group_handle_v1_add_listener(group, &group_listener, NULL);
}

static void mgr_workspace(void *data, struct ext_workspace_manager_v1 *m,
                           struct ext_workspace_handle_v1 *workspace) {
    (void)data; (void)m;
    if (ws_count < MAX_WS) {
        workspaces[ws_count].handle = workspace;
        workspaces[ws_count].index = ws_count;
        workspaces[ws_count].state = 0;
        workspaces[ws_count].name[0] = '\0';
        ws_count++;
        ext_workspace_handle_v1_add_listener(workspace, &ws_handle_listener, NULL);
    } else {
        ext_workspace_handle_v1_destroy(workspace);
    }
}

static void mgr_done(void *data, struct ext_workspace_manager_v1 *m) {
    (void)data; (void)m;
    write_active();
}

static void mgr_finished(void *data, struct ext_workspace_manager_v1 *m) {
    (void)data; (void)m;
    running = 0;
}

static const struct ext_workspace_manager_v1_listener mgr_listener = {
    .workspace_group = mgr_workspace_group,
    .workspace = mgr_workspace,
    .done = mgr_done,
    .finished = mgr_finished,
};

/* ── registry ──────────────────────────────────────────────────── */

static void registry_global(void *data, struct wl_registry *reg,
                            uint32_t name, const char *iface, uint32_t ver) {
    (void)data;
    if (strcmp(iface, ext_workspace_manager_v1_interface.name) == 0) {
        ws_manager = wl_registry_bind(reg, name,
                                      &ext_workspace_manager_v1_interface, 1);
        ext_workspace_manager_v1_add_listener(ws_manager, &mgr_listener, NULL);
    }
}

static void registry_global_remove(void *data, struct wl_registry *reg, uint32_t name) {
    (void)data; (void)reg; (void)name;
}

static const struct wl_registry_listener reg_listener = {
    .global = registry_global,
    .global_remove = registry_global_remove,
};

/* ── main ──────────────────────────────────────────────────────── */

static void handle_signal(int sig) {
    (void)sig;
    running = 0;
}

int main(void) {
    /* Build output path */
    const char *xdg = getenv("XDG_RUNTIME_DIR");
    if (!xdg) {
        fprintf(stderr, "XDG_RUNTIME_DIR not set\n");
        return 1;
    }
    snprintf(output_path, sizeof(output_path), "%s/labwc-active-workspace", xdg);
    snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", output_path);

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    struct wl_display *display = wl_display_connect(NULL);
    if (!display) {
        fprintf(stderr, "Cannot connect to Wayland display\n");
        return 1;
    }

    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &reg_listener, NULL);
    wl_display_roundtrip(display);

    if (!ws_manager) {
        fprintf(stderr, "Compositor does not support ext-workspace-v1\n");
        wl_display_disconnect(display);
        return 1;
    }

    /* Initial roundtrip to get workspace state */
    wl_display_roundtrip(display);

    while (running && wl_display_dispatch(display) != -1)
        ;

    unlink(output_path);
    wl_display_disconnect(display);
    return 0;
}
