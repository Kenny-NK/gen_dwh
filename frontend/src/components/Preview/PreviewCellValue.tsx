import React from "react";

import { MaskedValue } from "./MaskedValue";
import { isMaskedPreviewValue, stringifyPreviewValue } from "./previewValue";

interface PreviewCellValueProps {
  value: unknown;
}

export function PreviewCellValue({ value }: PreviewCellValueProps) {
  const textValue = stringifyPreviewValue(value);

  return (
    <div className="max-w-[24rem]" title={textValue}>
      {isMaskedPreviewValue(value) ? (
        <MaskedValue value={value} />
      ) : (
        <span className="block truncate whitespace-nowrap">{textValue}</span>
      )}
    </div>
  );
}
