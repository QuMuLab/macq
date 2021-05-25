#from ..trace import TraceList, Trace
import random
from macq.trace import TraceList, Trace, Step, Action, State, CustomObject, Fluent
from pathlib import Path
import tarski
from tarski.io import PDDLReader, FstripsWriter
from tarski.search import GroundForwardSearchModel
from tarski.search.operations import progress, is_applicable
from tarski.grounding import LPGroundingStrategy
from tarski.grounding.lp_grounding import ground_problem_schemas_into_plain_operators
from tarski.grounding.errors import ReachabilityLPUnsolvable
from tarski.syntax.ops import CompoundFormula, flatten
from collections import OrderedDict

class Generate:
    def __init__(self, dom : str, prob : str):
        super().__init__()

def generate_traces(dom : str, prob : str, plan_len : int, num_traces : int):
    """
	Generates traces randomly by uniformly sampling applicable actions to find plans
	of the given length.

	Arguments
	---------
	dom : str
		The domain filename.
	prob : str
		The problem filename.
	plan_len : int
		The length of each generated trace.
	num_traces : int
		The number of traces to generate.

	Returns
	-------
	traces : TraceList
		The list of traces generated.
    """

    # read the domain and problem
    reader = PDDLReader(raise_on_error=True)
    reader.parse_domain(dom)
    problem = reader.parse_instance(prob)
    # ground the problem
    operators = ground_problem_schemas_into_plain_operators(problem)
    instance = GroundForwardSearchModel(problem, operators)

    traces = TraceList()
    trace = Trace()
    num_generated = 0
    # loop through while the desired number of traces has not yet been generated
    while num_generated < num_traces:
        num_generated += 1
        trace.clear()
        state = problem.init
        # True if trace is fully generated to the desired length
        valid_trace = True
        # add more steps while the trace has not yet reached the desired length
        for j in range(plan_len):
            # find the next applicable actions
            app_act = instance.applicable(state)
            # get items from generator
            ls = []
            for item in app_act:
                ls.append(item)
            # if the trace reaches a dead end, disregard this trace and try again
            if ls == []:
                num_generated -= 1
                valid_trace = False
                break
            # pick a random applicable action and apply it
            act = random.choice(ls)
            # create the trace and progress the state
            macq_action = _tarski_act_to_macq(act, problem)
            macq_state = _tarski_state_to_macq(state, problem)
            step = Step(macq_action, macq_state)
            trace.append(step)
            state = progress(state, act)
        if valid_trace:
            traces.append(trace)
    return traces

def _extract_action_typing(problem: tarski.fstrips.problem.Problem):
    actions = problem.actions
    extracted_act_types = {}
    for act in actions:
        raw_types = str(actions[act])
        raw_types = raw_types[len(act) + 1: -1]
        raw_types = raw_types.split(',')
        params = []
        for raw_act in raw_types:
            params.append(raw_act.split(' ')[1])
        extracted_act_types[act] = params
    return extracted_act_types

def _extract_predicate_typing(writer: FstripsWriter):
    #can just take a problem
    extracted_pred_types = {}
    raw_pred = writer.get_predicates().split('\n')
    for i in range(len(raw_pred)):
        raw_pred[i] = raw_pred[i].lstrip()[1:-1]
        raw_pred[i] = raw_pred[i].split(' ')
        name = raw_pred[i][0]
        params = []
        for j in range(1, len(raw_pred[i])):
            check_hyph = '-'in raw_pred[i][j]
            if '-' not in raw_pred[i][j] and '?' not in raw_pred[i][j]:
                params.append(raw_pred[i][j])
        extracted_pred_types[name] = params    
    return extracted_pred_types

def _tarski_act_to_macq(act: tarski.fstrips.action.PlainOperator, problem: tarski.fstrips.problem.Problem):
    action_info = _typing_split(act.name, problem, True)
    precond = []
    if type(act.precondition) == CompoundFormula:
        raw_precond = act.precondition.subformulas
        for fluent in raw_precond:
            precond.append(_tarski_fluent_to_macq(str(fluent), problem))
    else:
        raw_precond = act.precondition
        precond.append(_tarski_fluent_to_macq(str(raw_precond), problem))
    
    (add, delete) = _effect_split(act, problem)
    action = Action(action_info['name'], action_info['objects'], precond, add, delete)
    return action

def _tarski_fluent_to_macq(raw: str, problem: tarski.fstrips.problem.Problem):
    # remove starting and ending parentheses, if necessary
    if raw[0] == '(':
        raw = raw[1:len(raw) - 1]
    test =  raw.split(' ')
    if 'not' in test:
        value = False
    else:
        value = True
    fluent = _typing_split(test[-1], problem, False)
    macq_fluent = Fluent(fluent['name'], fluent['objects'], value)
    return macq_fluent

def _effect_split(act: tarski.fstrips.action.PlainOperator, problem: tarski.fstrips.problem.Problem):
    effects = act.effects
    add = []
    delete = []
    for i in range(len(effects)):
        eff_str = effects[i].tostring()
        fluent = _tarski_fluent_to_macq(eff_str[3:], problem)
        if eff_str[:3] == 'ADD':
            add.append(fluent)
        else:
            delete.append(fluent)
    return(add, delete)

def _typing_split(raw: str, problem: tarski.fstrips.problem.Problem, is_action: bool):
    split = {}
    raw = raw.strip(')')
    name = raw.split('(')[0]
    raw = raw.replace(' ', '')
    param_names = raw.split('(')[1].split(',')
    num_param = len(param_names)
    obj_param = [] 

    if name == '=':
        types = ['object', 'object']
        name = 'equal'
    else:
        if is_action:
            act_types = _extract_action_typing(problem)
            types = act_types[name]
        else:
            fluent_types = _extract_predicate_typing(FstripsWriter(problem))
            types = fluent_types[name]

    for i in range(num_param):
        obj_param.append(CustomObject(types[i], param_names[i]))
    split['name'] = name
    split['objects'] = obj_param
    return split

def _tarski_state_to_macq(state: tarski.model.Model, problem: tarski.fstrips.problem.Problem):
    state = state.as_atoms()
    fluents = []
    for fluent in state:
        fluents.append(_tarski_fluent_to_macq(str(fluent), problem))
    return State(fluents)

if __name__ == "__main__":
    # exit out to the base macq folder so we can get to /tests 
    base = Path(__file__).parent.parent.parent
    dom = (base / 'tests/pddl_testing_files/domain.pddl').resolve()
    prob = (base / 'tests/pddl_testing_files/problem.pddl').resolve()
    print(generate_traces(dom, prob, 10, 10))