#!/usr/bin/env node

/**
 * CSV to JSON Converter for Princeton Dark Patterns Dataset
 * 
 * Converts dark-patterns.csv to dark-patterns.json for runtime use.
 * Preserves the original CSV unchanged.
 */

const fs = require("fs");
const path = require("path");

/**
 * Parse CSV safely, handling quoted fields and commas inside fields.
 * Returns an array of row objects.
 */
function parseCSV(csvContent) {
  const lines = csvContent.split("\n");
  if (lines.length < 2) return [];

  // Parse header
  const headerLine = lines[0];
  const headers = parseCSVLine(headerLine);

  // Parse data rows
  const rows = [];
  let currentRow = [];
  let buffer = "";
  let inQuotes = false;

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;

    // Process each character to handle quoted fields
    for (let j = 0; j < line.length; j++) {
      const char = line[j];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === "," && !inQuotes) {
        currentRow.push(buffer.trim().replace(/^"|"$/g, ""));
        buffer = "";
      } else {
        buffer += char;
      }
    }

    // Check if we're at the end of a line and not in quotes
    if (!inQuotes) {
      currentRow.push(buffer.trim().replace(/^"|"$/g, ""));
      if (currentRow.length === headers.length) {
        const rowObj = {};
        headers.forEach((header, idx) => {
          rowObj[header] = currentRow[idx] || "";
        });
        rows.push(rowObj);
      }
      currentRow = [];
      buffer = "";
    } else {
      buffer += "\n"; // Preserve newlines inside quoted fields
    }
  }

  return rows;
}

/**
 * Parse a single CSV line respecting quoted fields.
 */
function parseCSVLine(line) {
  const result = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      result.push(current.trim().replace(/^"|"$/g, ""));
      current = "";
    } else {
      current += char;
    }
  }

  if (current) {
    result.push(current.trim().replace(/^"|"$/g, ""));
  }

  return result;
}

/**
 * Normalize missing/empty values
 */
function normalizeValue(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed || trimmed.toLowerCase() === "n/a" || trimmed.toLowerCase() === "unknown") {
    return null;
  }
  return trimmed;
}

/**
 * Transform CSV row to JSON record
 */
function transformRecord(row) {
  return {
    pattern_string: normalizeValue(row["Pattern String"]),
    comment: normalizeValue(row["Comment"]),
    pattern_category: normalizeValue(row["Pattern Category"]),
    pattern_type: normalizeValue(row["Pattern Type"]),
    where_in_website: normalizeValue(row["Where in website?"]),
    deceptive: normalizeValue(row["Deceptive"]),
    website_page: normalizeValue(row["Website Page"])
  };
}

/**
 * Main conversion function
 */
function convertCSVToJSON(csvPath, jsonPath) {
  console.log(`Reading CSV from: ${csvPath}`);
  
  try {
    const csvContent = fs.readFileSync(csvPath, "utf8");
    console.log(`CSV file read successfully. Size: ${csvContent.length} bytes`);

    const rows = parseCSV(csvContent);
    console.log(`Parsed ${rows.length} records from CSV`);

    const records = rows.map(transformRecord);

    // Collect unique pattern categories and types for validation
    const categories = new Set(records.map(r => r.pattern_category).filter(Boolean));
    const types = new Set(records.map(r => r.pattern_type).filter(Boolean));

    console.log(`\nUnique Pattern Categories: ${Array.from(categories).sort().join(", ")}`);
    console.log(`Unique Pattern Types: ${Array.from(types).sort().join(", ")}`);

    const jsonObject = {
      source: "Princeton Dark Patterns at Scale",
      description: "Reference knowledge base derived from the Princeton dark-patterns dataset. This CSV contains observations of dark patterns from real websites. It serves as a taxonomy reference for behavioral pattern matching.",
      generation_date: new Date().toISOString(),
      record_count: records.length,
      unique_categories: Array.from(categories).sort(),
      unique_pattern_types: Array.from(types).sort(),
      records
    };

    const jsonContent = JSON.stringify(jsonObject, null, 2);
    fs.writeFileSync(jsonPath, jsonContent, "utf8");

    console.log(`\nJSON file written successfully to: ${jsonPath}`);
    console.log(`JSON file size: ${jsonContent.length} bytes`);
    console.log(`Total records: ${records.length}`);
  } catch (error) {
    console.error("Error during conversion:", error.message);
    process.exit(1);
  }
}

// Execute conversion
if (require.main === module) {
  const csvPath = path.join(__dirname, "dark-patterns.csv");
  const jsonPath = path.join(__dirname, "dark-patterns.json");

  convertCSVToJSON(csvPath, jsonPath);
}

module.exports = { parseCSV, transformRecord, convertCSVToJSON };
