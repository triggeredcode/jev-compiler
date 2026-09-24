/** Dependency-free runtime for a frozen Jev decision program. */

import { readFile } from "node:fs/promises";

export type JsonObject = Record<string, unknown>;

export interface Question {
  type: "choice" | "score" | "noul";
  instructions: string;
  criteria?: unknown;
}

export interface JevNode {
  id: string;
  type: "jev";
  questions: Record<string, Question>;
  when?: string;
  next?: string;
}

export interface BranchRule {
  when: string;
  return: string;
}

export interface BranchNode {
  id: string;
  type: "branch";
  rules: BranchRule[];
  default?: string;
  next?: string;
}

export interface ReturnNode {
  id: string;
  type: "return";
  value: string;
}

export type ProgramNode = JevNode | BranchNode | ReturnNode;

export interface DecisionProgram {
  version: 1;
  name: string;
  actions: string[];
  entrypoint?: string;
  jev_model: string;
  stages: ProgramNode[];
}

export interface ChoiceAnswer {
  type: "choice";
  choice: string;
  probabilities: Record<string, number>;
  confidence: number;
}

export interface ScoreAnswer {
  type: "score";
  score: number;
  probabilities: Record<string, number>;
  confidence: number;
  legend?: Record<string, string>;
}

export interface NoulAnswer {
  type: "noul";
  noul: number;
}

export type SystemOneAnswer = ChoiceAnswer | ScoreAnswer | NoulAnswer;

export interface SystemOneResult {
  model: string;
  answers: Record<string, SystemOneAnswer>;
}

export interface SystemOneProvider {
  evaluate(
    state: unknown,
    questions: Record<string, Question>,
    options: { model: string },
  ): Promise<SystemOneResult>;
}

export interface TraceEvent {
  stage_id: string;
  stage_type: ProgramNode["type"];
  started_at: string;
  output: JsonObject;
}

export interface DecisionResult {
  action: string;
  variables: JsonObject;
  trace: TraceEvent[];
}

export class ExpressionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExpressionError";
  }
}

type TokenKind = "number" | "string" | "identifier" | "operator" | "eof";

interface Token {
  kind: TokenKind;
  value: string;
  literal?: unknown;
}

function tokenize(expression: string): Token[] {
  const tokens: Token[] = [];
  let position = 0;

  while (position < expression.length) {
    const character = expression[position];
    if (/\s/.test(character)) {
      position += 1;
      continue;
    }

    const pair = expression.slice(position, position + 2);
    if (["==", "!=", "<=", ">=", "&&", "||"].includes(pair)) {
      tokens.push({ kind: "operator", value: pair });
      position += 2;
      continue;
    }
    if (["+", "-", "*", "/", "(", ")", ".", ",", "<", ">"].includes(character)) {
      tokens.push({ kind: "operator", value: character });
      position += 1;
      continue;
    }

    if (character === '"' || character === "'") {
      const quote = character;
      let value = "";
      position += 1;
      let closed = false;
      while (position < expression.length) {
        const item = expression[position];
        position += 1;
        if (item === quote) {
          closed = true;
          break;
        }
        if (item === "\\") {
          if (position >= expression.length) {
            throw new ExpressionError("unterminated string escape");
          }
          const escaped = expression[position];
          position += 1;
          const escapes: Record<string, string> = {
            n: "\n",
            r: "\r",
            t: "\t",
            "\\": "\\",
            '"': '"',
            "'": "'",
          };
          value += escapes[escaped] ?? escaped;
        } else {
          value += item;
        }
      }
      if (!closed) {
        throw new ExpressionError("unterminated string literal");
      }
      tokens.push({ kind: "string", value, literal: value });
      continue;
    }

    const number = expression.slice(position).match(/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/);
    if (number !== null) {
      tokens.push({ kind: "number", value: number[0], literal: Number(number[0]) });
      position += number[0].length;
      continue;
    }

    const identifier = expression.slice(position).match(/^[A-Za-z_][A-Za-z0-9_]*/);
    if (identifier !== null) {
      tokens.push({ kind: "identifier", value: identifier[0] });
      position += identifier[0].length;
      continue;
    }

    throw new ExpressionError(`invalid token at position ${position}`);
  }

  tokens.push({ kind: "eof", value: "" });
  return tokens;
}

function requireNumber(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ExpressionError("numeric operation requires finite numbers");
  }
  return value;
}

function compare(left: unknown, operator: string, right: unknown): boolean {
  if (operator === "==") return left === right;
  if (operator === "!=") return left !== right;
  if (
    !((typeof left === "number" && typeof right === "number") ||
      (typeof left === "string" && typeof right === "string"))
  ) {
    throw new ExpressionError("ordered comparisons require matching numbers or strings");
  }
  if (operator === "<") return left < right;
  if (operator === "<=") return left <= right;
  if (operator === ">") return left > right;
  if (operator === ">=") return left >= right;
  throw new ExpressionError(`comparison ${operator} is not allowed`);
}

class ExpressionParser {
  private position = 0;
  private readonly tokens: Token[];
  private readonly context: JsonObject;

  constructor(tokens: Token[], context: JsonObject) {
    this.tokens = tokens;
    this.context = context;
  }

  parse(): unknown {
    const value = this.parseOr();
    if (this.peek().kind !== "eof") {
      throw new ExpressionError(`unexpected token: ${this.peek().value}`);
    }
    return value;
  }

  private peek(): Token {
    return this.tokens[this.position];
  }

  private take(): Token {
    const token = this.peek();
    this.position += 1;
    return token;
  }

  private matches(...values: string[]): boolean {
    if (!values.includes(this.peek().value)) return false;
    this.position += 1;
    return true;
  }

  private expect(value: string): void {
    if (!this.matches(value)) {
      throw new ExpressionError(`expected ${value}, received ${this.peek().value || "end"}`);
    }
  }

  private parseOr(): unknown {
    let value = this.parseAnd();
    while (this.matches("or", "||")) {
      const right = this.parseAnd();
      value = Boolean(value) || Boolean(right);
    }
    return value;
  }

  private parseAnd(): unknown {
    let value = this.parseNot();
    while (this.matches("and", "&&")) {
      const right = this.parseNot();
      value = Boolean(value) && Boolean(right);
    }
    return value;
  }

  private parseNot(): unknown {
    if (this.matches("not")) return !Boolean(this.parseNot());
    return this.parseComparison();
  }

  private parseComparison(): unknown {
    let left = this.parseAdditive();
    let result: boolean | undefined;
    while (["==", "!=", "<", "<=", ">", ">="].includes(this.peek().value)) {
      const operator = this.take().value;
      const right = this.parseAdditive();
      result = (result ?? true) && compare(left, operator, right);
      left = right;
    }
    return result ?? left;
  }

  private parseAdditive(): unknown {
    let value = this.parseMultiplicative();
    while (["+", "-"].includes(this.peek().value)) {
      const operator = this.take().value;
      const right = this.parseMultiplicative();
      if (operator === "+" && typeof value === "string" && typeof right === "string") {
        value += right;
      } else {
        const leftNumber = requireNumber(value);
        const rightNumber = requireNumber(right);
        value = operator === "+" ? leftNumber + rightNumber : leftNumber - rightNumber;
      }
    }
    return value;
  }

  private parseMultiplicative(): unknown {
    let value = this.parseUnary();
    while (["*", "/"].includes(this.peek().value)) {
      const operator = this.take().value;
      const right = requireNumber(this.parseUnary());
      const left = requireNumber(value);
      if (operator === "/" && right === 0) throw new ExpressionError("division by zero");
      value = operator === "*" ? left * right : left / right;
    }
    return value;
  }

  private parseUnary(): unknown {
    if (this.matches("+")) return requireNumber(this.parseUnary());
    if (this.matches("-")) return -requireNumber(this.parseUnary());
    return this.parsePrimary();
  }

  private parsePrimary(): unknown {
    const token = this.peek();
    if (token.kind === "number" || token.kind === "string") {
      this.take();
      return token.literal;
    }
    if (token.value === "True" || token.value === "true") {
      this.take();
      return true;
    }
    if (token.value === "False" || token.value === "false") {
      this.take();
      return false;
    }
    if (this.matches("(")) {
      const value = this.parseOr();
      this.expect(")");
      return value;
    }
    if (token.kind !== "identifier") {
      throw new ExpressionError(`unexpected token: ${token.value || "end"}`);
    }

    const name = this.take().value;
    if (this.matches("(")) {
      const arguments_: unknown[] = [];
      if (!this.matches(")")) {
        do {
          arguments_.push(this.parseOr());
        } while (this.matches(","));
        this.expect(")");
      }
      return this.callFunction(name, arguments_);
    }

    if (!(name in this.context)) throw new ExpressionError(`unknown variable: ${name}`);
    let value: unknown = this.context[name];
    let path = name;
    while (this.matches(".")) {
      const attribute = this.take();
      if (attribute.kind !== "identifier") {
        throw new ExpressionError("attributes may only reference named result fields");
      }
      path += `.${attribute.value}`;
      if (typeof value !== "object" || value === null || !(attribute.value in value)) {
        throw new ExpressionError(`unknown variable: ${path}`);
      }
      value = (value as JsonObject)[attribute.value];
    }
    return value;
  }

  private callFunction(name: string, arguments_: unknown[]): unknown {
    if (name === "abs" && arguments_.length === 1) {
      return Math.abs(requireNumber(arguments_[0]));
    }
    if ((name === "min" || name === "max") && arguments_.length > 0) {
      const numbers = arguments_.map(requireNumber);
      return name === "min" ? Math.min(...numbers) : Math.max(...numbers);
    }
    throw new ExpressionError(`function ${name} is not allowed`);
  }
}

export function evaluateExpression(expression: string, context: JsonObject): unknown {
  return new ExpressionParser(tokenize(expression), context).parse();
}

function answerVariables(answer: SystemOneAnswer): unknown {
  if (answer.type === "noul") return answer.noul;
  if (answer.type === "choice") {
    return {
      value: answer.choice,
      choice: answer.choice,
      confidence: answer.confidence,
      probabilities: answer.probabilities,
    };
  }
  return {
    value: answer.score,
    score: answer.score,
    confidence: answer.confidence,
    probabilities: answer.probabilities,
    legend: answer.legend ?? {},
  };
}

export async function runProgram(
  program: DecisionProgram,
  state: unknown,
  provider: SystemOneProvider,
): Promise<DecisionResult> {
  if (program.stages.length === 0) throw new Error("program must contain at least one stage");
  const stages = new Map(program.stages.map((node) => [node.id, node]));
  const positions = new Map(program.stages.map((node, index) => [node.id, index]));
  let current: string | undefined = program.entrypoint ?? program.stages[0].id;
  const variables: JsonObject = {};
  const trace: TraceEvent[] = [];
  const visited = new Set<string>();

  while (current !== undefined) {
    if (visited.has(current)) throw new Error(`cycle detected at stage ${current}`);
    visited.add(current);
    const node = stages.get(current);
    if (node === undefined) throw new Error(`unknown stage: ${current}`);
    const started_at = new Date().toISOString();

    if (node.type === "jev") {
      if (node.when === undefined || Boolean(evaluateExpression(node.when, variables))) {
        const response = await provider.evaluate(state, node.questions, { model: program.jev_model });
        const output: JsonObject = {};
        for (const [key, answer] of Object.entries(response.answers)) {
          output[key] = answerVariables(answer);
        }
        const missing = Object.keys(node.questions).filter((key) => !(key in output)).sort();
        if (missing.length > 0) {
          throw new Error(`Jev response omitted answers: ${JSON.stringify(missing)}`);
        }
        Object.assign(variables, output);
        trace.push({
          stage_id: node.id,
          stage_type: node.type,
          started_at,
          output: { model: response.model, answers: output },
        });
      } else {
        trace.push({
          stage_id: node.id,
          stage_type: node.type,
          started_at,
          output: { skipped: true },
        });
      }
      current = node.next ?? nextStage(program, positions.get(node.id));
      continue;
    }

    if (node.type === "branch") {
      const matched = node.rules.find((rule) => Boolean(evaluateExpression(rule.when, variables)));
      const action = matched?.return ?? node.default;
      trace.push({
        stage_id: node.id,
        stage_type: node.type,
        started_at,
        output: { action },
      });
      if (action !== undefined) return { action, variables, trace };
      current = node.next ?? nextStage(program, positions.get(node.id));
      continue;
    }

    trace.push({
      stage_id: node.id,
      stage_type: node.type,
      started_at,
      output: { action: node.value },
    });
    return { action: node.value, variables, trace };
  }

  throw new Error("program ended without returning an action");
}

function nextStage(program: DecisionProgram, position: number | undefined): string | undefined {
  if (position === undefined) throw new Error("stage position is unavailable");
  return program.stages[position + 1]?.id;
}

export async function decide(
  state: unknown,
  provider: SystemOneProvider,
  programUrl: URL = new URL("./program.json", import.meta.url),
): Promise<DecisionResult> {
  const program = JSON.parse(await readFile(programUrl, "utf8")) as DecisionProgram;
  return runProgram(program, state, provider);
}
