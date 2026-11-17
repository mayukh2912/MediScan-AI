/** @type {import('next').NextConfig} */
// Static export: the site is plain HTML/JS, so it deploys on Vercel (Git or drag-and-drop "Vercel Drop"),
// Netlify, GitHub Pages or any static host. Security headers are set in vercel.json.
const nextConfig = {
  output: "export",
  reactStrictMode: true,
  poweredByHeader: false,
  trailingSlash: true,
  images: { unoptimized: true },
};
export default nextConfig;
