import copy
import sys

from loguru import logger

from .rulez import Rulez
from .workflow import Workflow

logger.add(sys.stderr, level="INFO")


class Blender:
    def __init__(self, rulez: Rulez):
        self.rulez = rulez
        self.main_wf = None
        self.main_stage_in = None
        self.main_stage_out = None
        self.start = None
        self.user_wf = None
        #    self.user_raw_wf_path = cwl
        self.inputs = []
        self.outputs = []

    @staticmethod
    def __prepare_step_run(step, name, main_node_in=None):
        if name not in step:
            step[name] = {}
        if "run" not in step[name]:
            step[name]["run"] = {}

        if "out" not in step[name]:
            step[name]["out"] = []
        else:
            if type(step[name]["out"]) is not list:
                raise Exception("Step output can be only an array")

        if "in" not in step[name]:
            step[name]["in"] = {}
            if main_node_in is not None and "in" in main_node_in:
                step[name]["in"] = copy.deepcopy(main_node_in["in"])

    @staticmethod
    def __to_cwl_dict(param: dict):
        new_p = dict(param)
        if "id" in new_p:
            pid = new_p["id"]
            del new_p["id"]
            return pid, new_p

    @staticmethod
    def __to_cwl_list(param: dict, name: str):
        new_p = dict(param)
        new_p["id"] = name
        return new_p

    @staticmethod
    def __is_dict_or_list(what):
        what_is_dict = None
        if type(what) is dict:
            what_is_dict = True
        elif type(what) is list:
            what_is_dict = False

        return what_is_dict

    @staticmethod
    def __add_to_in(where, what):
        if type(where) is list:
            where.append("%s:%s" % (what, what))
        elif type(where) is dict:
            where[what] = what

    @staticmethod
    def __add_input_to_in(where, what):
        if type(where) is list:
            where.append("%s:%s" % ("input", what))
        elif type(where) is dict:
            where["input"] = what

    @staticmethod
    def __exist_here(where, what):
        if type(where) is dict:
            return what in where.keys()

        if type(where) is list:
            for i in where:
                if "id" in i.keys() and i["id"] == what:
                    return True

        return False

    @staticmethod
    def __get_id(where):
        if type(where) is str:
            return where

        what = "id"
        if type(where) is dict:
            if what in where.keys():
                return where["id"]
            else:
                return None

        if type(where) is list:
            for i in where:
                if "id" in i.keys() and i["id"] == what:
                    return i["id"]

        return None

    def __create_on_stage_inputs(self, where, directories_out: dict):
        # # logger.debug(where)
        # # logger.debug(directories_out.__str__())

        inp = copy.deepcopy(self.user_wf.get_raw_all_inputs())

        if type(where) is not dict:
            raise Exception("on_stage -> in must be a dict")

        for it in inp:
            if type(it) is str:
                if it in directories_out:
                    where[it] = directories_out[it]
                else:
                    where[it] = it

            elif "id" in it:
                pid = it["id"]
                if pid in directories_out:
                    where[pid] = directories_out[pid]
                else:
                    where[pid] = pid

    def __connect_to_stage_out(self, what: dict, steps: dict):
        # logger.debug(what)
        # logger.debug(steps.keys())
        follow_node = self.rulez.get("/onstage/stage_out/follow_node")
        # logger.debug(follow_node)
        if follow_node != "" and follow_node in steps and "in" in steps[follow_node] and len(what) > 0:
            for d in what:
                steps[follow_node]["in"][d] = what[d]

    def __create_global_cwl_outputs(self, where, stage_out_dir):

        # # logger.debug(where)
        # # logger.debug(f"stage_out_dir {stage_out_dir}")
        inp = copy.deepcopy(self.user_wf.get_raw_all_outputs())
        # # logger.debug(inp)
        where_is_dict = self.__is_dict_or_list(where)
        if where_is_dict is None:
            raise Exception("__create_global_cwl_outputs where_is_dict is None")

        if inp:
            for it in inp:
                # # logger.debug(it)
                if type(it) is str:

                    if it in stage_out_dir:
                        if "outputSource" in inp[it]:
                            inp[it]["outputSource"] = []
                            inp[it]["outputSource"].append(stage_out_dir[it])

                    if where_is_dict:
                        where[it] = inp[it]
                    else:
                        where.append(self.__to_cwl_list(inp[it], it))
                else:

                    if "id" in it:
                        if it["id"] in stage_out_dir:
                            if "outputSource" in it:
                                it["outputSource"] = []
                                it["outputSource"].append(stage_out_dir[it["id"]])

                        if where_is_dict:
                            pid, psa = self.__to_cwl_dict(it)
                            where[pid] = psa
                        else:
                            where.append(it)

                if not stage_out_dir:
                    # there's no stage out step, the result comes from the on_stage step
                    # # logger.debug(f"add {it['id']}")
                    it["outputSource"] = [f"on_stage/{it['id']}"]
                    if where_is_dict:
                        pid, psa = self.__to_cwl_dict(it)
                        where[pid] = psa
                    else:
                        where.append(it)

    def __find_in_inputs(self, what):
        for it in self.inputs:
            if it.id == what:
                return copy.deepcopy(it)

        return None

    def __change_input_type(self, src: dict, name=""):
        where = copy.deepcopy(src)
        v = self.__find_in_inputs(name)
        if v is None:
            return where

        if "type" in where:

            if v.is_array and "?" in where["type"]:
                where["type"] = self.rulez.get("/cwl/OptionalInput/Directory[]")  # 'string[]'
                return where
            elif v.is_array:
                where["type"] = self.rulez.get("/cwl/GlobalInput/Directory[]")  # 'string[]':
                return where
            elif "?" in where["type"]:
                where["type"] = self.rulez.get("/cwl/OptionalInput/Directory")
                return where
            else:
                where["type"] = self.rulez.get("/cwl/GlobalInput/Directory")
                return where

        return where

    def __get_essential(self, where: dict, id: dict = None):
        ret = dict()

        if "label" in where:
            ret["label"] = where["label"]

        if "doc" in where:
            ret["doc"] = where["doc"]

        if id is not None and id in where:
            ret[id] = where[id]

        if "type" in where:
            ret["type"] = where["type"]

        return self.__change_input_type(ret)

    def add_secret_parameter(self, parameter, what):

        # logger.debug(parameter)

        if "hints" in self.main_wf.keys() and "hints" in what.keys():
            # # logger.debug("hints defined")
            if (
                "cwltool:Secrets" in self.main_wf["hints"].keys()
                and "cwltool:Secrets" in what["hints"].keys()
            ):
                # # logger.debug("secrets defined")
                if parameter in what["hints"]["cwltool:Secrets"]["secrets"]:
                    # logger.debug(f"adding {parameter} as secret")
                    self.start["hints"]["cwltool:Secrets"]["secrets"].append(parameter)

    def __update_zone_with_template(self, where, what):
        if "inputs" in self.main_stage_in:
            the_i = copy.deepcopy(what["inputs"])

            for it in the_i:
                inner_id = self.__get_id(it)
                obj = dict()
                if not self.__exist_here(where, inner_id):
                    if type(it) is str:  # the_i is a dict
                        obj = copy.deepcopy(the_i[it])
                        if "id" not in obj:
                            obj["id"] = inner_id
                    else:
                        obj = copy.deepcopy(it)

                    if type(where) is dict:
                        where[inner_id] = self.__get_essential(obj, inner_id)
                    else:
                        where.append(self.__get_essential(obj, inner_id))

                self.add_secret_parameter(parameter=it, what=what)

            # # logger.debug(self.main_wf)

            # if type(id) is str:
            #     inner_id = id
            # else:
            #     inner_id =
            #
            # if __exist_here(where,)
            #
            # if type(where) is dict:

            # if the_i_what:
            #     print(str(it))
            # else:
            #     print(str(it))

    def __create_global_cwl_inputs(self, where):

        inp = copy.deepcopy(self.user_wf.get_raw_all_inputs())

        where_is_dict = self.__is_dict_or_list(where)
        if where_is_dict is None:
            raise Exception("__create_global_cwl_inputs where_is_dict is None")

        # if where_is_dict is not None:
        if inp:
            for it in inp:
                # # logger.debug(it)
                if type(it) is str:
                    if where_is_dict:
                        where[it] = self.__change_input_type(inp[it], it)
                    else:
                        where.append(self.__to_cwl_list(self.__change_input_type(inp[it], it), it))
                else:
                    if where_is_dict:
                        pid, psa = self.__to_cwl_dict(self.__change_input_type(it, it["id"]))
                        where[pid] = psa
                    else:
                        where.append(self.__change_input_type(it, it["id"]))

        self.__update_zone_with_template(where, self.main_stage_in)
        self.__update_zone_with_template(where, self.main_stage_out)

        # print(the_i)

        # to_add = self.rulez.get("/cwl/stage_out/user_inputs")
        # for it in to_add:
        #     if where_is_dict:
        #         where[it] = to_add[it]
        #     else:
        #         where.append(copy.deepcopy(self.__to_cwl_list(to_add[it], it)))

    def __add_inputs_store_to_stage_out(self, where: dict):
        where_is_dict = self.__is_dict_or_list(where)
        if where_is_dict is None:
            raise Exception("__create_global_cwl_inputs where_is_dict is None")

        to_add = self.rulez.get("/cwl/stage_out/user_inputs")
        for it in to_add:
            where[it] = it

    def __add_stage_in_graph_cwl(self):

        # driver = self.rulez.get('/onstage/driver')

        if "inputs" not in self.main_stage_in:
            self.main_stage_in["inputs"] = {}

        if "outputs" not in self.main_stage_in:
            self.main_stage_in["outputs"] = {}

        if "inputs" not in self.main_stage_out:
            self.main_stage_out["inputs"] = {}

        if "outputs" not in self.main_stage_out:
            self.main_stage_out["outputs"] = {}

        if "inputs" not in self.start:
            self.start["inputs"] = {}

        if "outputs" not in self.start:
            self.start["outputs"] = {}

        self.__create_global_cwl_inputs(self.start["inputs"])

        connection_node_node_stage_in = self.rulez.get("/onstage/stage_in/connection_node")
        if connection_node_node_stage_in == "":
            connection_node_node_stage_in = "node_stage_in"

        if self.start is None:
            raise Exception("maincwl.yaml not defined")

        if "steps" not in self.start:
            # steps does not exist
            self.start["steps"] = {}

        nodes_out = {}
        steps = self.start["steps"]
        cursor = 0
        start_node_name = connection_node_node_stage_in
        overwrite_input = self.rulez.get("/onstage/stage_in/input/template/overwrite")

        in_main_template = None

        if connection_node_node_stage_in in steps and "in" in steps[connection_node_node_stage_in]:
            in_main_template = copy.deepcopy(steps[connection_node_node_stage_in])

        # stage in

        # Case where stage in only used for aws credentials
        if not self.inputs:
            logger.info("Adding stage-in step for credentials only") 
            self.__prepare_step_run(steps, start_node_name, in_main_template)
            the_command = copy.deepcopy(self.main_stage_in)  # self.main_stage_in.copy()
            the_command_inputs = the_command["inputs"]
            the_command_outputs = the_command["outputs"]

            # Add default inputs
            if type(the_command_inputs) is list:
                for i in the_command_inputs:
                    self.__add_to_in(steps[start_node_name]["in"], i["id"])
            elif type(the_command_inputs) is dict:
                for i in the_command_inputs:
                    self.__add_to_in(steps[start_node_name]["in"], i)

            steps[start_node_name]["run"] = the_command

            cursor = cursor + 1
            start_node_name = "%s_%d" % (start_node_name, cursor)

        # Case where stagein used to load data for workflow
        for it in self.inputs:
            # print(f'Nodo: {start_node_name}  ')
            self.__prepare_step_run(steps, start_node_name, in_main_template)

            self.__add_input_to_in(steps[start_node_name]["in"], it.id)

            the_command = copy.deepcopy(self.main_stage_in)  # self.main_stage_in.copy()
            the_command_inputs = the_command["inputs"]
            the_command_outputs = the_command["outputs"]

            if overwrite_input and len(the_command_inputs) > 0:
                if type(the_command_inputs) is list:
                    for i in the_command_inputs:
                        self.__add_to_in(steps[start_node_name]["in"], i["id"])
                elif type(the_command_inputs) is dict:
                    for i in the_command_inputs:
                        self.__add_to_in(steps[start_node_name]["in"], i)

            # why am I using copy.deepcopy??
            # https://ttl255.com/yaml-anchors-and-aliases-and-how-to-disable-them/
            # logger.debug(it)

            if it.is_array:
                the_val = copy.deepcopy(self.rulez.get("/cwl/stage_in/Directory[]"))
            elif it.is_optional:
                the_val = copy.deepcopy(self.rulez.get("/cwl/stage_in/Directory?"))
            else:
                the_val = copy.deepcopy(self.rulez.get("/cwl/stage_in/Directory"))

            # the_val = (
            #     copy.deepcopy(self.rulez.get("/cwl/stage_in/Directory[]"))
            #     if it.is_array
            #     else copy.deepcopy(self.rulez.get("/cwl/stage_in/Directory"))
            # )

            # scatter feature
            if it.is_array:
                the_val = self.rulez.get("/cwl/stage_in/Directory")

            # logger.debug(the_val)

            if type(the_command_inputs) is list:
                the_val["id"] = copy.deepcopy(it.id)
                the_command_inputs.append(the_val)
            elif type(the_command_inputs) is dict:
                the_command_inputs["input"] = copy.deepcopy(the_val)

            steps[start_node_name]["run"] = the_command

            # add outputs to command

            if it.is_optional:
                command_out = copy.deepcopy(
                    self.rulez.get("/cwl/outputBindingResult/command/Directory?")
                )
            else:
                command_out = copy.deepcopy(self.rulez.get("/cwl/outputBindingResult/command/Directory"))

            command_id = "%s_out" % it.id
            nodes_out[it.id] = "%s/%s_out" % (start_node_name, it.id)
            if type(the_command_outputs) is list:
                command_out["id"] = command_id
                the_command_outputs.append(command_out)
            elif type(the_command_outputs) is dict:
                the_command_outputs[command_id] = command_out

            # add step output
            steps[start_node_name]["out"].append(command_id)

            # check scattering
            if it.is_array:
                steps[start_node_name]["scatter"] = "input"
                steps[start_node_name]["scatterMethod"] = self.rulez.get(
                    "/onstage/stage_in/if_scatter/scatterMethod"
                )

            cursor = cursor + 1
            start_node_name = "%s_%d" % (start_node_name, cursor)

        # ON_STAGE!
        on_stage_node = self.rulez.get("/onstage/on_stage/connection_node")
        if on_stage_node == "":
            on_stage_node = "on_stage"

        self.__prepare_step_run(steps, on_stage_node)

        steps[on_stage_node]["run"] = f"#{self.user_wf.get_id()}"

        if steps[on_stage_node]["run"] == "":
            raise Exception('Workflow without "id"')

        self.__create_on_stage_inputs(steps[on_stage_node]["in"], nodes_out)

        # stage out
        connection_node_node_stage_out = self.rulez.get("/onstage/stage_out/connection_node")
        if connection_node_node_stage_out == "":
            connection_node_node_stage_out = "node_stage_out"

        cursor = 0
        start_node_name = connection_node_node_stage_out

        nodes_out.clear()
        # logger.debug(f"outputs: {self.outputs}")

        if len(self.outputs) == 0:
            # no stage-out node(s) so the on_stage step lists the user workflow outputs
            outputs = self.user_wf.get_raw_all_outputs()
            # logger.debug(outputs)
            for it in outputs:
                steps[on_stage_node]["out"].append(it["id"])

        for it in self.outputs:
            steps[on_stage_node]["out"].append(it.id)

            self.__prepare_step_run(steps, start_node_name)

            if type(steps[start_node_name]["in"]) is list:
                steps[start_node_name]["in"].append("%s:%s/%s" % ("wf_outputs", on_stage_node, it.id))
            elif type(steps[start_node_name]["in"]) is dict:
                steps[start_node_name]["in"]["wf_outputs"] = "%s/%s" % (
                    on_stage_node,
                    it.id,
                )

            # self.__add_inputs_store_to_stage_out(steps[start_node_name]['in'])

            the_command = copy.deepcopy(self.main_stage_out)  # self.main_stage_in.copy()
            the_command_inputs = the_command["inputs"]
            the_command_outputs = the_command["outputs"]

            # appending the stageout template outputs to the macro cwl outputs
            for stage_out_output_id in the_command_outputs:
                nodes_out[stage_out_output_id] = "%s/%s" % (
                    start_node_name,
                    stage_out_output_id,
                )
                self.start["outputs"][stage_out_output_id] = dict()
                self.start["outputs"][stage_out_output_id]["id"] = stage_out_output_id
                self.start["outputs"][stage_out_output_id]["outputSource"] = []
                self.start["outputs"][stage_out_output_id]["outputSource"].append(
                    nodes_out[stage_out_output_id]
                )
                self.start["outputs"][stage_out_output_id]["type"] = the_command_outputs[
                    stage_out_output_id
                ]["type"]

            if overwrite_input and len(the_command_inputs) > 0:
                if type(the_command_inputs) is list:
                    for i in the_command_inputs:
                        self.__add_to_in(steps[start_node_name]["in"], i["id"])
                elif type(the_command_inputs) is dict:
                    for i in the_command_inputs:
                        self.__add_to_in(steps[start_node_name]["in"], i)

            the_val = (
                copy.deepcopy(self.rulez.get("/cwl/stage_out/Directory[]"))
                if it.is_array
                else copy.deepcopy(self.rulez.get("/cwl/stage_out/Directory"))
            )

            # scatter feature
            if it.is_array and self.rulez.get("/onstage/stage_out/scatter"):
                the_val = self.rulez.get("/cwl/stage_out/Directory")

            if type(the_command_inputs) is list:
                the_val["id"] = "wf_outputs"
                the_command_inputs.append(the_val)
            elif type(the_command_inputs) is dict:
                the_command_inputs["wf_outputs"] = the_val
            steps[start_node_name]["run"] = the_command

            command_out = (
                copy.deepcopy(self.rulez.get("/cwl/outputBindingResult/command/Directory[]"))
                if it.is_array
                else copy.deepcopy(self.rulez.get("/cwl/outputBindingResult/command/Directory"))
            )

            command_id = "%s_out" % it.id
            nodes_out[it.id] = "%s/%s_out" % (start_node_name, it.id)
            if type(the_command_outputs) is list:
                command_out["id"] = command_id
                the_command_outputs.append(command_out)
            elif type(the_command_outputs) is dict:
                the_command_outputs[command_id] = command_out

            # add step output, including the stageout outputs
            for id in the_command_outputs:
                steps[start_node_name]["out"].append(id)

            # check scattering
            if it.is_array and self.rulez.get("/onstage/stage_out/scatter"):
                steps[start_node_name]["scatter"] = "wf_outputs"
                steps[start_node_name]["scatterMethod"] = self.rulez.get(
                    "/onstage/stage_in/stage_out/scatterMethod"
                )

            cursor = cursor + 1
            start_node_name = "%s_%d" % (start_node_name, cursor)

        self.__create_global_cwl_outputs(self.start["outputs"], nodes_out)
        self.__connect_to_stage_out(nodes_out, steps)

        return self.start

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
        self.start = copy.deepcopy(self.main_wf)

        self.start = self.__add_stage_in_graph_cwl()

        return self.start
