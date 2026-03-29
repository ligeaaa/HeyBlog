declare module "react-cytoscapejs" {
  import type { ComponentType, CSSProperties } from "react";
  import type cytoscape from "cytoscape";

  export type CytoscapeComponentProps = {
    elements?: cytoscape.ElementDefinition[];
    stylesheet?: cytoscape.StylesheetJson;
    layout?: cytoscape.LayoutOptions;
    style?: CSSProperties;
    minZoom?: number;
    maxZoom?: number;
    cy?: (instance: cytoscape.Core) => void;
  };

  const CytoscapeComponent: ComponentType<CytoscapeComponentProps>;
  export default CytoscapeComponent;
}

declare module "cytoscape-fcose" {
  import type cytoscape from "cytoscape";

  const fcose: cytoscape.Ext;
  export default fcose;
}
