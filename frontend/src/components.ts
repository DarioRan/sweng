/** The twelve classes of backend/app/vision/categories.json (ADR 0002), for people. */

export type Component = { id: string; name: string; also: string[] };

export const COMPONENTS: Component[] = [
  { id: "rear_derailleur", name: "Rear derailleur", also: ["gears", "rear mech", "shifting"] },
  { id: "front_derailleur", name: "Front derailleur", also: ["front mech", "gears"] },
  { id: "cassette", name: "Cassette", also: ["sprockets", "cogs", "freewheel", "rear gears"] },
  { id: "chain", name: "Chain", also: ["links"] },
  { id: "crankset", name: "Crankset", also: ["cranks", "chainrings", "crank arm"] },
  { id: "bottom_bracket", name: "Bottom bracket", also: ["bb", "crank bearing"] },
  { id: "pedal", name: "Pedal", also: ["pedals", "cleats"] },
  {
    id: "shift_brake_lever",
    name: "Brake or shift lever",
    also: ["shifter", "brake lever", "trigger", "grip shift"],
  },
  { id: "disc_brake_caliper", name: "Disc brake caliper", also: ["disc brake", "brake pads"] },
  { id: "disc_rotor", name: "Disc rotor", also: ["rotor", "brake disc"] },
  { id: "rim_brake_caliper", name: "Rim brake caliper", also: ["caliper brake", "rim brake"] },
  { id: "v_brake", name: "V-brake", also: ["linear pull", "rim brake", "brake arms"] },
];

const BY_ID = new Map(COMPONENTS.map((c) => [c.id, c]));

export function componentName(id: string): string {
  return BY_ID.get(id)?.name ?? id.replaceAll("_", " ");
}

/** Search by name, always available (T-406): matches the name or a common word for it. */
export function searchComponents(query: string): Component[] {
  const q = query.trim().toLowerCase();
  if (!q) return COMPONENTS;
  return COMPONENTS.filter(
    (c) => c.name.toLowerCase().includes(q) || c.also.some((a) => a.includes(q)),
  );
}

/** A few questions to start from, per component: the kind the manuals answer. */
export const SUGGESTIONS: Record<string, string[]> = {
  rear_derailleur: [
    "How do I adjust the high and low limit screws?",
    "What is the tightening torque for the derailleur mounting bolt?",
  ],
  front_derailleur: ["How do I adjust the front derailleur?", "What is the mounting torque?"],
  cassette: ["What is the tightening torque for the lock ring?", "How do I install the cassette?"],
  chain: ["How do I join the chain?", "How do I check chain wear?"],
  crankset: ["What is the tightening torque for the crank arm bolts?"],
  bottom_bracket: ["What is the tightening torque for the bottom bracket?"],
  pedal: ["How tight should the pedal be?", "How do I adjust the cleat tension?"],
  shift_brake_lever: ["How do I adjust the brake lever reach?"],
  disc_brake_caliper: ["How do I replace the brake pads?", "How do I bleed the brake?"],
  disc_rotor: ["What is the tightening torque for the rotor lock ring?"],
  rim_brake_caliper: ["How do I adjust the brake shoe clearance?"],
  v_brake: ["How do I adjust the brake shoes?", "How do I install the V-brake?"],
};
