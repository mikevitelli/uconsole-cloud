import { defineType, defineField } from "sanity";

export const backupLog = defineType({
  name: "backupLog",
  title: "Backup Log",
  type: "document",
  fields: [
    defineField({
      name: "ranAt",
      title: "Ran At",
      type: "datetime",
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: "status",
      title: "Status",
      type: "string",
      options: {
        list: [
          { title: "Success", value: "success" },
          { title: "Partial", value: "partial" },
          { title: "Failed", value: "failed" },
        ],
      },
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: "modules",
      title: "Modules Run",
      type: "array",
      of: [{ type: "string" }],
      options: {
        list: [
          { title: "Packages", value: "packages" },
          { title: "Configs", value: "configs" },
          { title: "Scripts", value: "scripts" },
          { title: "Browser", value: "browser" },
          { title: "Desktop", value: "desktop" },
          { title: "Git/SSH", value: "git-ssh" },
        ],
      },
    }),
    defineField({
      name: "notes",
      title: "Notes",
      type: "text",
      rows: 3,
    }),
  ],
  orderings: [
    {
      title: "Date (newest)",
      name: "dateDesc",
      by: [{ field: "ranAt", direction: "desc" }],
    },
  ],
  preview: {
    select: { date: "ranAt", status: "status" },
    prepare({ date, status }) {
      const d = date ? new Date(date).toLocaleDateString() : "No date";
      return { title: d, subtitle: status };
    },
  },
});
