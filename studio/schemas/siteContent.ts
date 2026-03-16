import { defineType, defineField } from "sanity";

export const siteContent = defineType({
  name: "siteContent",
  title: "Site Content",
  type: "document",
  fields: [
    defineField({
      name: "site",
      title: "Site",
      type: "object",
      fields: [
        defineField({ name: "title", title: "Title", type: "string" }),
        defineField({
          name: "description",
          title: "Description",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "landing",
      title: "Landing",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "description",
          title: "Description",
          type: "string",
        }),
        defineField({
          name: "signInButton",
          title: "Sign In Button",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "repoLinker",
      title: "Repo Linker",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "description",
          title: "Description",
          type: "string",
        }),
        defineField({
          name: "placeholder",
          title: "Placeholder",
          type: "string",
        }),
        defineField({
          name: "selectPlaceholder",
          title: "Select Placeholder",
          type: "string",
        }),
        defineField({
          name: "buttonText",
          title: "Button Text",
          type: "string",
        }),
        defineField({
          name: "loadingButton",
          title: "Loading Button",
          type: "string",
        }),
        defineField({
          name: "loadingText",
          title: "Loading Text",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "dashboard",
      title: "Dashboard",
      type: "object",
      fields: [
        defineField({
          name: "headerTitle",
          title: "Header Title",
          type: "string",
        }),
        defineField({
          name: "unlinkButton",
          title: "Unlink Button",
          type: "string",
        }),
        defineField({
          name: "signOutButton",
          title: "Sign Out Button",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "backupCoverage",
      title: "Backup Coverage",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "items",
          title: "Items",
          type: "array",
          of: [
            {
              type: "object",
              fields: [
                defineField({ name: "key", title: "Key", type: "string" }),
                defineField({ name: "name", title: "Name", type: "string" }),
                defineField({
                  name: "defaultDetail",
                  title: "Default Detail",
                  type: "string",
                }),
              ],
              preview: {
                select: { title: "name", subtitle: "key" },
              },
            },
          ],
        }),
      ],
    }),
    defineField({
      name: "backupHistory",
      title: "Backup History",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "sparklineLabel",
          title: "Sparkline Label",
          type: "string",
        }),
        defineField({
          name: "totalLabel",
          title: "Total Label",
          type: "string",
        }),
        defineField({
          name: "latestLabel",
          title: "Latest Label",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "packageInventory",
      title: "Package Inventory",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "totalLabel",
          title: "Total Label",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "browserExtensions",
      title: "Browser Extensions",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "statLabel",
          title: "Stat Label",
          type: "string",
        }),
        defineField({
          name: "emptyState",
          title: "Empty State",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "scriptsManifest",
      title: "Scripts Manifest",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "emptyState",
          title: "Empty State",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "repoStats",
      title: "Repo Stats",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
        defineField({
          name: "sizeLabel",
          title: "Size Label",
          type: "string",
        }),
        defineField({
          name: "branchLabel",
          title: "Branch Label",
          type: "string",
        }),
        defineField({
          name: "lastPushLabel",
          title: "Last Push Label",
          type: "string",
        }),
        defineField({
          name: "visibilityLabel",
          title: "Visibility Label",
          type: "string",
        }),
      ],
    }),
    defineField({
      name: "repoStructure",
      title: "Repo Structure",
      type: "object",
      fields: [
        defineField({ name: "heading", title: "Heading", type: "string" }),
      ],
    }),
  ],
  preview: {
    prepare() {
      return { title: "Site Content" };
    },
  },
});
