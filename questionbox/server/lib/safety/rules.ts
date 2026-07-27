/**
 * WonderBox safety rules — the editable allow/deny configuration.
 *
 * In Stage 5 these move into Supabase so they can be edited from the parent
 * dashboard without a code change. For now they live here as the DEFAULT_RULES,
 * and everything else (the deterministic classifier, the LLM prompts) is built
 * from this single source of truth.
 *
 * Philosophy: ANSWER only simple, factual, kid-appropriate questions. DEFER
 * everything subjective, scary, or adult to a parent. Default to DEFER when
 * unsure. Over-blocking is acceptable; under-blocking is not.
 */

export type Decision = "answer" | "defer" | "refuse";

export interface TopicRule {
  id: string;
  label: string;
  /** Regex source strings (matched case-insensitively, word-aware). */
  patterns: string[];
}

export interface SafetyRules {
  version: string;
  /** Topics we are willing to answer (subject to the LLM gates). */
  allow: TopicRule[];
  /** Topics we always defer to a parent (never answered). */
  deny: TopicRule[];
  /** Attempts to change the rules / jailbreak — refused. */
  refuse: TopicRule[];
}

export const DEFAULT_RULES: SafetyRules = {
  version: "2026-07-27",
  allow: [
    { id: "how-things-work", label: "how things work", patterns: ["how does", "how do", "why does", "why do", "what makes", "how is .* made"] },
    { id: "animals", label: "animals", patterns: ["animal", "dog", "cat", "lion", "fish", "bird", "insect", "bug", "dinosaur", "cow", "horse", "elephant", "spider", "snake", "frog", "bee"] },
    { id: "nature", label: "nature", patterns: ["tree", "plant", "flower", "rain", "cloud", "weather", "ocean", "river", "mountain", "volcano", "rainbow", "wind", "leaf", "leaves"] },
    { id: "space", label: "space", patterns: ["space", "moon", "sun", "star", "planet", "mars", "earth", "rocket", "galaxy", "comet", "astronaut"] },
    { id: "science", label: "science", patterns: ["science", "gravity", "magnet", "energy", "light", "sound", "water", "ice", "float", "melt", "electric", "atom", "temperature"] },
    { id: "math", label: "simple math", patterns: ["plus", "minus", "add", "subtract", "times", "how many", "count", "\\bnumber\\b", "what is \\d", "\\d\\s*\\+\\s*\\d"] },
    { id: "shapes-colors", label: "shapes and colors", patterns: ["shape", "circle", "square", "triangle", "rectangle", "\\bcolor\\b", "\\bcolour\\b"] },
    { id: "definitions", label: "definitions", patterns: ["what is a", "what is an", "what does .* mean", "what are"] },
    { id: "spelling", label: "spelling", patterns: ["how do you spell", "how to spell", "spell the word", "can you spell", "^spell "] },
    { id: "geography", label: "simple geography", patterns: ["country", "continent", "\\bocean\\b", "capital city", "where is the"] },
  ],
  deny: [
    { id: "opinions", label: "opinions", patterns: ["what do you think", "do you like", "your favorite", "favourite", "who is better", "should i", "is it good", "is it bad", "prettier", "coolest", "best .* ever", "your opinion"] },
    { id: "feelings", label: "feelings and emotions", patterns: ["are you happy", "are you sad", "do you love", "love you", "do you feel", "how do you feel", "are you scared", "are you lonely", "i feel", "i'm sad", "im sad", "why am i sad", "\\bjealous\\b", "\\bhate\\b"] },
    { id: "news", label: "current events and news", patterns: ["\\bnews\\b", "current event", "happening in the world", "what happened today", "latest", "right now in the world"] },
    { id: "politics", label: "politics", patterns: ["president", "election", "\\bvot", "democrat", "republican", "government", "political", "prime minister", "politic", "\\bmayor\\b", "congress"] },
    { id: "religion", label: "religion", patterns: ["\\bgod\\b", "jesus", "allah", "bible", "church", "\\bpray", "heaven", "\\bhell\\b", "religio", "buddha", "muslim", "christian", "jewish", "\\bsoul\\b"] },
    { id: "death", label: "death", patterns: ["\\bdie\\b", "\\bdies\\b", "died", "dying", "death", "\\bdead\\b", "funeral", "\\bgrave\\b", "afterlife", "pass away", "passed away"] },
    { id: "violence", label: "violence and weapons", patterns: ["\\bgun", "\\bknife", "weapon", "\\bbomb", "shoot", "\\bwar\\b", "\\bfight", "\\bblood", "punch", "\\bkill", "\\bhurt", "\\bstab", "\\battack"] },
    { id: "scary", label: "scary things", patterns: ["monster", "\\bghost", "\\bscary", "nightmare", "\\bwitch", "zombie", "demon", "devil", "kidnap", "haunted", "creepy"] },
    { id: "sex", label: "sex and where babies come from", patterns: ["\\bsex", "\\bsexy", "penis", "vagina", "where do babies come", "where babies come", "how are babies made", "make a baby", "making babies", "pregnan", "\\bboobs?\\b", "breast", "\\bnaked\\b", "private parts"] },
    { id: "medical", label: "medical and health", patterns: ["\\bsick\\b", "medicine", "\\bdoctor", "hospital", "disease", "\\bvirus", "covid", "cancer", "\\bpain\\b", "\\bshot\\b", "vaccine", "symptom", "\\bdrug", "\\bpills?\\b", "why am i sick", "medication"] },
    { id: "real-people", label: "specific real people", patterns: ["donald trump", "joe biden", "\\belon\\b", "taylor swift", "kim kardashian", "\\bputin\\b", "is santa real", "is santa claus real", "who is the president"] },
    { id: "money", label: "money and buying", patterns: ["\\bmoney\\b", "how much does .* cost", "\\bprice\\b", "expensive", "\\bcheap\\b", "\\bdollars?\\b", "how do i get rich", "\\bsalary\\b", "\\bafford", "\\bbuy\\b"] },
  ],
  refuse: [
    { id: "rule-change", label: "changing the rules", patterns: ["ignore .* rules", "ignore your instruction", "forget your instruction", "new rule", "you can answer anything", "pretend you", "jailbreak", "override", "you are allowed to", "stop following", "disregard"] },
  ],
};
