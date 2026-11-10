"use client";

import { type CSSProperties } from "react";
import EmojiPicker, { EmojiStyle, Theme, type EmojiClickData } from "emoji-picker-react";

const compactEmojiPickerStyle = {
  "--epr-emoji-size": "22px",
  "--epr-emoji-padding": "3px",
  "--epr-search-input-height": "32px",
  "--epr-category-navigation-button-size": "24px",
  "--epr-header-padding": "10px",
  "--epr-picker-border-radius": "8px",
  border: "0",
  backgroundColor: "transparent",
} as CSSProperties;

export function CompactAgentEmojiPicker({
  searchPlaceholder,
  height = 300,
  onEmojiClick,
}: {
  searchPlaceholder: string;
  height?: number;
  onEmojiClick: (emojiData: EmojiClickData) => void;
}) {
  return (
    <EmojiPicker
      className="nyro-agent-emoji-picker"
      theme={Theme.DARK}
      emojiStyle={EmojiStyle.NATIVE}
      width="100%"
      height={height}
      style={compactEmojiPickerStyle}
      searchPlaceholder={searchPlaceholder}
      previewConfig={{ showPreview: false }}
      skinTonesDisabled
      onEmojiClick={onEmojiClick}
    />
  );
}
