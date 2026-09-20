import mermaid from './mermaid.esm.mjs';

mermaid.initialize({ startOnLoad: false });

const c1 = `C4Context
  title System Context Diagram - Photo Meta Organizer
  Person(photographer, "Photographer & Curator", "Browses high-resolution galleries, searches metadata, rates, flags picks, inspects EXIF, and curates staging collections.")
  Person(dataset_mgr, "Dataset Manager / Engineer", "Ingests 20GB+ photo collections, synchronizes incremental changes, monitors throughput, and exports curated datasets.")
  
  System(photo_system, "Photo Meta Organizer Platform", "High-performance metadata indexing, multi-criteria search, WebP thumbnail streaming, and interactive photo organization system.")
  
  System_Ext(local_fs, "Local Filesystem Storage", "Local file system directory hierarchies containing original RAW, JPEG, PNG, HEIC, and TIFF image assets.")
  System_Ext(cloud_s3, "Amazon S3 Object Store", "Optional remote cloud bucket for photo archives and binary byte stream retrieval via boto3.")
  System_Ext(web_browser, "Modern Web Browser", "Client execution runtime for React 19 SPA, handling WebGL maps, OffscreenCanvas histograms, and 60 FPS DOM virtualization.")

  Rel(photographer, photo_system, "Browses galleries, searches, filters, inspects EXIF, and curates", "HTTPS / Web UI")
  Rel(dataset_mgr, photo_system, "Executes batch indexing, synchronizes metadata, and inspects stats", "CLI / Terminal")
  Rel(photo_system, local_fs, "Scans directories, reads image binary streams, and writes metadata.json", "OS File I/O")
  Rel(photo_system, cloud_s3, "Streams remote image bytes on demand via S3 SDK", "HTTPS / REST")
  Rel(photo_system, web_browser, "Delivers React SPA assets, JSON REST responses, and WebP thumbnail streams", "HTTP / JSON")`;

try {
  await mermaid.parse(c1);
  console.log('C1 parsed successfully!');
} catch (e) {
  console.error('C1 error:', e.message);
  console.error(e.str || e.hash || '');
}
