import { useEffect, useId, useRef, useState } from "react";
import { searchPlaces } from "../api/client";
import type { PlaceSuggestion } from "../api/types";

interface Props {
  id: string;
  value: string;
  onChange: (text: string) => void;
  onPick: (place: PlaceSuggestion) => void;
  onSubmit: () => void; // Enter with nothing highlighted: search for exactly what was typed
  near?: { lat: number; lon: number } | null; // the map being looked at: results around it rank first
}

const DEBOUNCE_MS = 300; // wait for a pause in typing, so one request covers a whole word
const MIN_ONLINE_CHARS = 3;

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The parts of `text` that match a word the user typed are wrapped in <mark>. */
function highlight(text: string, query: string) {
  const words = query.split(/\s+/).filter(Boolean);
  if (words.length === 0) return text;
  const parts = text.split(new RegExp(`(${words.map(escapeRegExp).join("|")})`, "i"));
  return parts.map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part));
}

function tag(place: PlaceSuggestion) {
  if (place.source === "preset") return "ready-made";
  if (place.source === "recent") return "used before";
  return place.kind;
}

/** A text box that suggests places while you type (arrow keys + Enter, or click). */
export default function PlaceSearchBox({ id, value, onChange, onPick, onSubmit, near }: Props) {
  const listId = useId();
  const [items, setItems] = useState<PlaceSuggestion[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const picked = useRef<string | null>(null); // text that came from choosing a suggestion: don't search for it again
  const query = value.trim();
  const nearRef = useRef(near); // read when a search fires; a different map alone doesn't re-run one
  nearRef.current = near;

  useEffect(() => {
    if (picked.current !== null) {
      if (picked.current === query) return;
      picked.current = null;
    }
    setActive(-1);
    if (query.length === 0) {
      setItems([]);
      setNote(null);
      setStatus("idle");
      return;
    }
    setStatus("loading"); // the previous list stays visible meanwhile, so the box doesn't flicker
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      searchPlaces(query, controller.signal, nearRef.current)
        .then((result) => {
          setItems(result.suggestions);
          setNote(result.note);
          setStatus("done");
        })
        .catch(() => {
          if (controller.signal.aborted) return; // superseded by a newer keystroke
          setItems([]);
          setNote("Suggestions are unavailable right now. Press Enter to search for what you typed.");
          setStatus("done");
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  const showList = open && query.length > 0 && (items.length > 0 || status !== "idle");

  function pick(place: PlaceSuggestion) {
    picked.current = place.label;
    setItems([]);
    setNote(null);
    setStatus("idle");
    setOpen(false);
    onPick(place);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!showList) setOpen(true);
      else if (items.length > 0) setActive((i) => (i + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (items.length > 0) setActive((i) => (i <= 0 ? items.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      if (showList && items[active]) {
        e.preventDefault();
        pick(items[active]);
      } else {
        setOpen(false);
        onSubmit();
      }
    } else if (e.key === "Escape" && showList) {
      e.preventDefault();
      setOpen(false);
    }
  }

  let footer = "";
  if (status === "loading") footer = "Searching…";
  else if (note) footer = note;
  else if (items.length === 0) footer = query.length < MIN_ONLINE_CHARS ? "Keep typing…" : `No suggestions. Press Enter to search for “${query}” anyway.`;
  else if (items.some((p) => p.source === "online")) footer = "Suggestions by Photon · © OpenStreetMap contributors";

  return (
    <div className="combo">
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        autoFocus
        maxLength={200}
        value={value}
        placeholder="e.g. Koramangala, Bengaluru"
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <div className="combo-popup">
          {items.length > 0 && (
            <ul id={listId} role="listbox" className="combo-list">
              {items.map((place, i) => (
                <li
                  key={`${place.label}|${place.lat}|${place.lon}`}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  className={i === active ? "combo-option combo-active" : "combo-option"}
                  onMouseDown={(e) => e.preventDefault()} // keep focus in the input so the click isn't lost to a blur
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(place)}
                >
                  <span className="combo-title">{highlight(place.title, query)}</span>
                  <span className="combo-tag">{tag(place)}</span>
                  {place.detail && <span className="combo-detail">{place.detail}</span>}
                </li>
              ))}
            </ul>
          )}
          {footer && (
            <div className="combo-foot" role="status">
              {footer}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
