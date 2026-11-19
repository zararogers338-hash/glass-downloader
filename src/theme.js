import {QuantizerCelebi,Score,Hct,TonalPalette,hexFromArgb} from '@material/material-color-utilities';

export function paletteFromPixels(pixels) {
  const [seed] = Score.score(QuantizerCelebi.quantize(pixels, 96));
  const hue = Hct.fromInt(seed).hue;
  const tone = (chroma, value) => hexFromArgb(TonalPalette.fromHueAndChroma(hue,chroma).tone(value));
  return {
    seed: hexFromArgb(seed), accent: tone(48,82), onAccent: tone(28,14),
    surface: tone(10,11), panel: tone(12,17), line: tone(12,32), muted: tone(12,76), ink: tone(8,96)
  };
}
