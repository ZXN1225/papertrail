# R02 v25 parser structural integrity check

Offline parser output: 9 approved papers, 217 pages, 3254 elements.

Mechanical consistency only; it does not score extraction accuracy, semantic table correctness, OCR, image interpretation, or retrieval. Active SQLite remains on v21.

- Duplicate element IDs: 0
- Invalid/out-of-page bounding boxes: 0
- Empty-text elements: 90
- Table logical rows/cells: 299/1175
- Figure captions: 58

## Element types

| Type | Count |
|---|---:|
| `figure_caption` | 58 |
| `heading` | 90 |
| `image_region` | 90 |
| `paragraph` | 2990 |
| `table` | 26 |

## Table structure status

| Status | Count |
|---|---:|
| `grid_body_columns_preserved_header_unreliable` | 9 |
| `grid_columns_preserved_bbox_incomplete` | 1 |
| `pdfplumber_grid` | 14 |
| `visual_lines_only_unstructured` | 2 |

## Warnings

| Warning | Elements |
|---|---:|
| `captioned_table_geometry_incomplete` | 11 |
| `multi_column_reading_order_ambiguous` | 451 |
| `out_of_page_text_excluded` | 475 |
| `rotated_text_excluded` | 838 |
| `sparse_table_candidates_rejected` | 742 |
| `table_body_grid_preserved_no_body_text_cut` | 10 |
| `table_header_geometry_unreliable` | 118 |
| `table_structure_unavailable_visual_lines_only` | 36 |
| `two_column_layout_detected` | 129 |

## Caption-image relations

| Status | Captions |
|---|---:|
| `ambiguous` | 4 |
| `matched` | 49 |
| `unmatched` | 5 |

Raw summary: Git-ignored local artifact `backend/reports/live_eval/R02-v25-structural-integrity.json`; no paper text is reproduced.
