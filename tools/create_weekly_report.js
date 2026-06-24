const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, HeadingLevel,
        AlignmentType, WidthType, BorderStyle, ShadingType, LevelFormat, PageBreak } = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const headerShading = { fill: "2E75B6", type: ShadingType.CLEAR };
const lightShading = { fill: "D5E8F0", type: ShadingType.CLEAR };

const doc = new Document({
  styles: {
    default: { 
      document: { 
        run: { font: "Arial", size: 24 } 
      } 
    },
    paragraphStyles: [
      { 
        id: "Heading1", 
        name: "Heading 1", 
        basedOn: "Normal", 
        next: "Normal", 
        quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } 
      },
      { 
        id: "Heading2", 
        name: "Heading 2", 
        basedOn: "Normal", 
        next: "Normal", 
        quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 180, after: 100 }, outlineLevel: 1 } 
      },
    ]
  },
  numbering: {
    config: [
      { 
        reference: "bullets",
        levels: [{ 
          level: 0, 
          format: LevelFormat.BULLET, 
          text: "•", 
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } 
        }] 
      },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: {
          width: 12240,
          height: 15840
        },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    children: [
      // Title
      new Paragraph({
        children: [new TextRun({ text: "SolRiver Solar Portfolio", bold: true, size: 36, color: "1F4E78" })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 100 }
      }),
      new Paragraph({
        children: [new TextRun({ text: "Weekly Health Report", bold: true, size: 28, color: "2E75B6" })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 240 }
      }),
      
      // Report Period
      new Paragraph({
        children: [new TextRun({ text: "Report Period: June 1–8, 2026", italics: true })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 360 }
      }),

      // Executive Summary
      new Paragraph({
        text: "Executive Summary",
        heading: HeadingLevel.HEADING_1
      }),
      new Paragraph({
        children: [new TextRun("During the week of June 1–8, your portfolio experienced "), 
                  new TextRun({ text: "32 total alerts", bold: true }), 
                  new TextRun(" affecting "), 
                  new TextRun({ text: "15 sites", bold: true }), 
                  new TextRun(". Of these, "), 
                  new TextRun({ text: "20 alerts remain unresolved", bold: true }), 
                  new TextRun(" and require immediate attention. The primary concern is "), 
                  new TextRun({ text: "C & B Graham Energy", bold: true }), 
                  new TextRun(", which accounted for 41% of weekly alerts (13 of 32).")]
      }),
      new Paragraph({
        children: [new TextRun("")],
        spacing: { after: 240 }
      }),

      // Critical Issues
      new Paragraph({
        text: "Critical Issues Requiring Immediate Action",
        heading: HeadingLevel.HEADING_1
      }),
      
      new Paragraph({
        text: "1. C & B Graham Energy — 9 Unresolved Alerts",
        heading: HeadingLevel.HEADING_2
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Inverter Faults (Solectria XGI 1000/1500 Series)", bold: true }), 
                  new TextRun(" — Multiple units reporting low voltage conditions, phase lock loop failures, and AC switch shutdowns. Impact: Likely power loss from affected units.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Device Communication Failures (3 instances)", bold: true }), 
                  new TextRun(" — Wiring problems suspected between devices and gateway. Impact: Loss of monitoring and control.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Solar FlexRack Tracker Alert", bold: true }), 
                  new TextRun(" — System monitor detected out-of-range/fault condition. Impact: Tracker may not be optimizing for sun position.")]
      }),
      new Paragraph({
        children: [new TextRun("")],
        spacing: { after: 240 }
      }),

      new Paragraph({
        text: "2. Eagle — 4 Unresolved Alerts",
        heading: HeadingLevel.HEADING_2
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Inverter Insulation Resistance Low", bold: true }), 
                  new TextRun(" — Isolation error detected. Risk of safety/efficiency issue.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "External Fan Errors", bold: true }), 
                  new TextRun(" — Multiple cooling fan failures. Risk of thermal shutdown.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Device & Gateway Heartbeat Failures", bold: true }), 
                  new TextRun(" — Wiring or power supply issue between gateway and devices.")]
      }),
      new Paragraph({
        children: [new TextRun("")],
        spacing: { after: 240 }
      }),

      new Paragraph({
        text: "3. Longleaf Pine Solar, LLC — 2 Unresolved Alerts",
        heading: HeadingLevel.HEADING_2
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Transformer Vacuum Fault", bold: true }), 
                  new TextRun(" — Pressure reading is critically low (< –5 psi). Oil cooling may be compromised.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Device Communication Loss", bold: true }), 
                  new TextRun(" — Wiring/connection issue.")]
      }),
      new Paragraph({
        children: [new TextRun("")],
        spacing: { after: 360 }
      }),

      // Most Problematic Sites Table
      new Paragraph({
        text: "Most Problematic Sites",
        heading: HeadingLevel.HEADING_1
      }),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [5000, 2180, 2180],
        rows: [
          new TableRow({
            children: [
              new TableCell({
                borders, shading: headerShading, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 5000, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun({ text: "Site Name", bold: true, color: "FFFFFF" })] })]
              }),
              new TableCell({
                borders, shading: headerShading, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun({ text: "Total Alerts", bold: true, color: "FFFFFF" })] })]
              }),
              new TableCell({
                borders, shading: headerShading, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun({ text: "Unresolved", bold: true, color: "FFFFFF" })] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 5000, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun("C & B Graham Energy")] })]
              }),
              new TableCell({
                borders, shading: lightShading, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun({ text: "13", bold: true })] })]
              }),
              new TableCell({
                borders, shading: { fill: "FCE4D6", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun({ text: "9", bold: true, color: "C65911" })] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 5000, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun("Eagle")] })]
              }),
              new TableCell({
                borders, shading: lightShading, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun("4")] })]
              }),
              new TableCell({
                borders, shading: { fill: "FCE4D6", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun({ text: "4", bold: true, color: "C65911" })] })]
              })
            ]
          }),
          new TableRow({
            children: [
              new TableCell({
                borders, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 5000, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun("Longleaf Pine Solar, LLC")] })]
              }),
              new TableCell({
                borders, shading: lightShading, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun("2")] })]
              }),
              new TableCell({
                borders, shading: { fill: "FCE4D6", type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
                width: { size: 2180, type: WidthType.DXA },
                children: [new Paragraph({ children: [new TextRun({ text: "2", bold: true, color: "C65911" })] })]
              })
            ]
          }),
        ]
      }),
      new Paragraph({
        children: [new TextRun("")],
        spacing: { after: 360 }
      }),

      // Alert Summary
      new Paragraph({
        text: "Alert Summary by Type",
        heading: HeadingLevel.HEADING_1
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Rule Tool Alerts: 11 ", bold: true }), 
                  new TextRun("— Communication and performance test failures across multiple sites.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Device Communication: 5 ", bold: true }), 
                  new TextRun("— Wiring/connection issues between gateways and field devices.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Inverter Faults (Solectria XGI): 7 ", bold: true }), 
                  new TextRun("— Low voltage, phase lock loop, and shutdown alerts.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "String Inverter Faults (.Chint/Solectria/Canadian): 3 ", bold: true }), 
                  new TextRun("— Insulation and fan errors.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Other: 6 ", bold: true }), 
                  new TextRun("(Tracker, Transformer, Heartbeat alerts)")]
      }),
      new Paragraph({
        children: [new TextRun("")],
        spacing: { after: 360 }
      }),

      // Recommendations
      new Paragraph({
        text: "Immediate Action Plan",
        heading: HeadingLevel.HEADING_1
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "C & B Graham Energy (Priority 1)", bold: true }), 
                  new TextRun(" — Schedule site visit within 48 hours. Inspect inverter electrical connections, validate low-voltage readings, and check AC switch status. Device communication failures suggest a wiring/connector issue.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Eagle (Priority 1)", bold: true }), 
                  new TextRun(" — Address external fan failures and heartbeat/gateway communication issues. Likely wiring or power supply at the gateway.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Longleaf Pine Solar, LLC (Priority 1)", bold: true }), 
                  new TextRun(" — Transformer vacuum fault is critical. Contact transformer OEM immediately to assess cooling system status.")]
      }),
      new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: "Follow-up", bold: true }), 
                  new TextRun(" — After resolving critical issues, review remaining 8 unresolved alerts and acknowledge/reassign as needed.")]
      }),
      new Paragraph({
        children: [new TextRun("")],
        spacing: { after: 360 }
      }),

      // Footer
      new Paragraph({
        children: [new TextRun({ text: "Generated: June 9, 2026", italics: true, size: 20 })],
        alignment: AlignmentType.RIGHT
      }),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("/sessions/festive-jolly-noether/mnt/SolRivers-Brain/Weekly_Health_Report_June1-8.docx", buffer);
  console.log("Report created successfully!");
});
