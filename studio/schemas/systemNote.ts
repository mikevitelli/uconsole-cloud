import { defineType, defineField } from "sanity";

export const systemNote = defineType({
  name: "systemNote",
  title: "System Note",
  type: "document",
  fields: [
    defineField({
      name: "title",
      title: "Title",
      type: "string",
      validation: (rule) => rule.required(),
    }),
    defineField({
      name: "body",
      title: "Body",
      type: "text",
      rows: 4,
    }),
    defineField({
      name: "category",
      title: "Category",
      type: "string",
      options: {
        list: [
          { title: "Packages", value: "packages" },
          { title: "Config", value: "config" },
          { title: "Scripts", value: "scripts" },
          { title: "Hardware", value: "hardware" },
          { title: "General", value: "general" },
        ],
      },
      initialValue: "general",
    }),
    defineField({
      name: "pinned",
      title: "Pinned",
      type: "boolean",
      initialValue: false,
    }),
  ],
  orderings: [
    {
      title: "Created (newest)",
      name: "createdDesc",
      by: [{ field: "_createdAt", direction: "desc" }],
    },
  ],
  preview: {
    select: { title: "title", category: "category" },
    prepare({ title, category }) {
      return { title, subtitle: category };
    },
  },
});
