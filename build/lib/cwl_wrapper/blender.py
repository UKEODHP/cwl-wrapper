from .rulez import Rulez
from .workflow import Workflow

import copy


class Blender:
    def __init__(self, kwargs, rulez: Rulez):
        self.rulez = rulez
        self.main_wf = None
        self.main_stage_in = None
        self.main_stage_out = None

        self.user_wf = None
        self.user_raw_wf_path = kwargs['cwl']
        self.inputs = []
        self.outputs = []

    @staticmethod
    def __prepare_step_run(step, name):
        if name not in step:
            step[name] = {}
        if 'run' not in step[name]:
            step[name]['run'] = {}

        if 'out' not in step[name]:
            step[name]['out'] = []
        else:
            if type(step[name]['out']) is not list:
                raise Exception('Step output can be only array')

        if 'in' not in step[name]:
            step[name]['in'] = {}

    @staticmethod
    def __to_cwl_dict(param: dict):
        new_p = dict(param)
        if 'id' in new_p:
            pid = new_p['id']
            del new_p['id']
            return pid, new_p

    @staticmethod
    def __to_cwl_list(param: dict, name: str):
        new_p = dict(param)
        new_p['id'] = name
        return new_p

    @staticmethod
    def __is_dict_or_list(what):
        what_is_dict = None
        if type(what) is dict:
            what_is_dict = True
        elif type(what) is list:
            what_is_dict = False

        return what_is_dict

    def __create_on_stage_inputs(self, where, directories_out: dict):
        inp = copy.deepcopy(self.user_wf.get_raw_all_inputs())

        if type(where) is not dict:
            raise Exception('on_stage -> in mast be a dict')

        for it in inp:
            if 'id' in it:
                pid = it['id']
                if pid in directories_out:
                    where[pid] = directories_out[pid]
                else:
                    where[pid] = pid

    def __create_global_cwl_outputs(self, where, stage_out_dir):

        inp = copy.deepcopy(self.user_wf.get_raw_all_outputs())

        where_is_dict = self.__is_dict_or_list(where)
        if where_is_dict is None:
            raise Exception('__create_global_cwl_outputs where_is_dict is None')

        if inp:
            for it in inp:
                if type(it) is str:

                    if it in stage_out_dir:
                        if 'outputSource' in inp[it]:
                            inp[it]['outputSource'] = []
                            inp[it]['outputSource'].append(stage_out_dir[it])

                    if where_is_dict:
                        where[it] = inp[it]
                    else:
                        where.append(self.__to_cwl_list(inp[it], it))
                else:

                    if 'id' in it:
                        if it['id'] in stage_out_dir:
                            if 'outputSource' in it:
                                it['outputSource'] = []
                                it['outputSource'].append(stage_out_dir[it['id']])

                        if where_is_dict:
                            pid, psa = self.__to_cwl_dict(it)
                            where[pid] = psa
                        else:
                            where.append(it)

    def __create_global_cwl_inputs(self, where):

        inp = copy.deepcopy(self.user_wf.get_raw_all_inputs())

        where_is_dict = self.__is_dict_or_list(where)
        if where_is_dict is None:
            raise Exception('__create_global_cwl_inputs where_is_dict is None')

        # if where_is_dict is not None:
        if inp:
            for it in inp:
                if type(it) is str:
                    if where_is_dict:
                        where[it] = inp[it]
                    else:
                        where.append(self.__to_cwl_list(inp[it], it))
                else:
                    if where_is_dict:
                        pid, psa = self.__to_cwl_dict(it)
                        where[pid] = psa
                    else:
                        where.append(it)

    def __add_stage_in_graph_cwl(self, start):

        # driver = self.rulez.get('/onstage/driver')

        if 'inputs' not in self.main_stage_in:
            self.main_stage_in['inputs'] = {}

        if 'outputs' not in self.main_stage_in:
            self.main_stage_in['outputs'] = {}

        if 'inputs' not in self.main_stage_out:
            self.main_stage_out['inputs'] = {}

        if 'outputs' not in self.main_stage_out:
            self.main_stage_out['outputs'] = {}

        if 'inputs' not in start:
            start['inputs'] = {}

        if 'outputs' not in start:
            start['outputs'] = {}

        self.__create_global_cwl_inputs(start['inputs'])

        connection_node_node_stage_in = self.rulez.get('/onstage/stage_in/connection_node')
        if connection_node_node_stage_in == '':
            connection_node_node_stage_in = 'node_stage_in'

        if start is None:
            raise Exception('maincwl.yaml not defined')

        if 'steps' not in start:
            # steps does not exist
            start['steps'] = {}

        nodes_out = {}
        steps = start['steps']
        cursor = 0
        start_node_name = connection_node_node_stage_in

        # stage in
        for it in self.inputs:
            # print(str(it))
            self.__prepare_step_run(steps, start_node_name)

            if type(steps[start_node_name]['in']) is list:
                steps[start_node_name]['in'].append('%s:%s' % (it.id, it.id))
            elif type(steps[start_node_name]['in']) is dict:
                steps[start_node_name]['in'][it.id] = it.id

            the_command = copy.deepcopy(self.main_stage_in)  # self.main_stage_in.copy()
            the_command_inputs = the_command['inputs']
            the_command_outputs = the_command['outputs']

            # why am I using copy.deepcopy??
            # https://ttl255.com/yaml-anchors-and-aliases-and-how-to-disable-them/
            the_val = copy.deepcopy(self.rulez.get('/cwl/Directory[]')) if it.is_array else copy.deepcopy(
                self.rulez.get('/cwl/Directory'))

            if type(the_command_inputs) is list:
                the_val['id'] = it.id
                the_command_inputs.append(the_val)
            elif type(the_command_inputs) is dict:
                the_command_inputs[it.id] = the_val

            steps[start_node_name]['run'] = the_command

            # add outputs to command
            command_out = copy.deepcopy(self.rulez.get('/cwl/outputBindingResult/command'))
            command_id = '%s_out' % it.id
            nodes_out[it.id] = '%s/%s_out' % (start_node_name, it.id)
            if type(the_command_outputs) is list:
                command_out['id'] = command_id
                the_command_outputs.append(command_out)
            elif type(the_command_outputs) is dict:
                the_command_outputs[command_id] = command_out

            # add step output
            steps[start_node_name]['out'].append(command_id)

            # check scattering
            if it.is_array:
                steps[start_node_name]['scatter'] = it.id
                steps[start_node_name]['scatterMethod'] = self.rulez.get('/onstage/stage_in/if_scatter/scatterMethod')

            cursor = cursor + 1
            start_node_name = '%s_%d' % (start_node_name, cursor)

        # ON_STAGE!
        on_stage_node = self.rulez.get('/onstage/on_stage/connection_node')
        if on_stage_node == '':
            on_stage_node = 'on_stage'

        self.__prepare_step_run(steps, on_stage_node)

        steps[on_stage_node]['run'] = '#%s' % self.user_wf.get_id()

        if steps[on_stage_node]['run'] == '':
            raise Exception('Workflow without "id"')

        self.__create_on_stage_inputs(steps[on_stage_node]['in'], nodes_out)

        # stage out
        connection_node_node_stage_out = self.rulez.get('/onstage/stage_out/connection_node')
        if connection_node_node_stage_out == '':
            connection_node_node_stage_out = 'node_stage_out'

        cursor = 0
        start_node_name = connection_node_node_stage_out

        nodes_out.clear()
        for it in self.outputs:
            steps[on_stage_node]['out'].append(it.id)

            self.__prepare_step_run(steps, start_node_name)

            if type(steps[start_node_name]['in']) is list:
                steps[start_node_name]['in'].append('%s:%s/%s' % (it.id, on_stage_node, it.id))
            elif type(steps[start_node_name]['in']) is dict:
                steps[start_node_name]['in'][it.id] = '%s/%s' % (on_stage_node, it.id)

            the_command = copy.deepcopy(self.main_stage_out)  # self.main_stage_in.copy()
            the_command_inputs = the_command['inputs']
            the_command_outputs = the_command['outputs']

            the_val = copy.deepcopy(self.rulez.get('/cwl/Directory[]')) if it.is_array else copy.deepcopy(
                self.rulez.get('/cwl/Directory'))

            if type(the_command_inputs) is list:
                the_val['id'] = it.id
                the_command_inputs.append(the_val)
            elif type(the_command_inputs) is dict:
                the_command_inputs[it.id] = the_val

            steps[start_node_name]['run'] = the_command

            # add outputs to command
            command_out = copy.deepcopy(self.rulez.get('/cwl/outputBindingResult/command'))
            command_id = '%s_out' % it.id
            nodes_out[it.id] = '%s/%s_out' % (start_node_name, it.id)
            if type(the_command_outputs) is list:
                command_out['id'] = command_id
                the_command_outputs.append(command_out)
            elif type(the_command_outputs) is dict:
                the_command_outputs[command_id] = command_out
            # add step output
            steps[start_node_name]['out'].append(command_id)

            # check scattering
            if it.is_array:
                steps[start_node_name]['scatter'] = it.id
                steps[start_node_name]['scatterMethod'] = self.rulez.get('/onstage/stage_in/if_scatter/scatterMethod')

            cursor = cursor + 1
            start_node_name = '%s_%d' % (start_node_name, cursor)

        self.__create_global_cwl_outputs(start['outputs'], nodes_out)

        return start

    def set_main_workflow(self, wf_main):
        self.main_wf = wf_main

    def set_stage_in(self, wf_in):
        self.main_stage_in = wf_in

    def set_stage_out(self, wf_out):
        self.main_stage_out = wf_out

    def set_user_workflow(self, wf: Workflow):
        self.user_wf = wf
        self.inputs = self.user_wf.get_inputs_directory()
        self.outputs = self.user_wf.get_outputs_directory()
        # a = self.user_wf.get_raw_all_inputs()

    def get_output(self):

        start = copy.deepcopy(self.main_wf)

        start = self.__add_stage_in_graph_cwl(start)


        # if self.rulez.get('/onstage/driver') == 'cwl':
        #     if self.rulez.get('/output/type') == '$graph':
        #         self.__add_stage_in_graph_cwl( )
        #
        #     else:
        #         raise Exception("Non $graph request")
        # else:
        #     raise Exception('Driver onstage: ' + self.rulez.get('/output/driver') + ' not found')

        return start