import { defineType, defineField } from "sanity";

export const systemProfile = defineType({
  name: "systemProfile",
  title: "System Profile",
  type: "document",
  fields: [
    defineField({
      name: "hostname",
      title: "Hostname",
      type: "string",
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: "os",
      title: "OS",
      type: "string",
    }),
    defineField({
      name: "device",
      title: "Device",
      type: "string",
      description: "e.g. uConsole, DevTerm, desktop",
    }),
    defineField({
      name: "repo",
      title: "Backup Repo",
      type: "string",
      description: "GitHub owner/repo for this system's backups",
    }),
    defineField({
      name: "description",
      title: "Description",
      type: "text",
      rows: 3,
    }),
    defineField({
      name: "active",
      title: "Active",
      type: "boolean",
      initialValue: true,
    }),
  ],
  preview: {
    select: { title: "hostname", subtitle: "device" },
  },
});
