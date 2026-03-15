import { defineConfig, definePlugin } from "sanity";
import { structureTool } from "sanity/structure";
import { visionTool } from "@sanity/vision";
import { schemaTypes } from "./schemas";
import type { StructureBuilder } from "sanity/structure";
import { DashboardTool } from "./components/DashboardTool";

const dashboardPlugin = definePlugin({
  name: "uconsole-dashboard",
  tools: [
    {
      name: "dashboard",
      title: "Dashboard",
      component: DashboardTool,
    },
  ],
});

export default defineConfig({
  name: "uconsole-studio",
  title: "uConsole Studio",

  projectId: process.env.SANITY_STUDIO_PROJECT_ID || "PLACEHOLDER",
  dataset: process.env.SANITY_STUDIO_DATASET || "production",

  plugins: [
    dashboardPlugin(),
    structureTool({
      structure: (S: StructureBuilder) =>
        S.list()
          .title("Content")
          .items([
            S.listItem()
              .title("Site Content")
              .id("siteContent")
              .child(
                S.document()
                  .schemaType("siteContent")
                  .documentId("siteContent")
                  .title("Site Content")
              ),
            S.divider(),
            ...S.documentTypeListItems().filter(
              (item) => item.getId() !== "siteContent"
            ),
          ]),
    }),
    visionTool(),
  ],

  schema: {
    types: schemaTypes,
  },
});
