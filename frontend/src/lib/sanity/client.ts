import { createClient } from "@sanity/client";

export const sanityClient = createClient({
  projectId: "jdm1m5uf",
  dataset: "production",
  apiVersion: "2024-01-01",
  useCdn: true,
});
