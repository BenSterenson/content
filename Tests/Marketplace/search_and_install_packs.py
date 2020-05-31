from __future__ import print_function

import os
import ast
import json
import demisto_client
from threading import Thread, Lock
from demisto_sdk.commands.common.tools import print_color, LOG_COLORS, run_threads_list
from Tests.Marketplace.marketplace_services import IGNORED_FILES, PACKS_FULL_PATH

IGNORED_FILES = ['NonSupported', 'ApiModules', '__init__.py']
PACKS_FULL_PATH = 'Packs'

PACK_METADATA_FILE = 'pack_metadata.json'


def get_pack_display_name(pack_id):
    metadata_path = os.path.join(PACKS_FULL_PATH, pack_id, PACK_METADATA_FILE)
    if pack_id and os.path.isfile(metadata_path):
        with open(metadata_path, 'r') as json_file:
            pack_metadata = json.load(json_file)
        return pack_metadata.get('name')
    return ''


def get_pack_data_from_results(search_results, pack_display_name):
    if not search_results:
        return {}
    for pack in search_results:
        if pack.get('name') == pack_display_name:
            return {
                'id': pack.get('id'),
                'version': pack.get('currentVersion')
            }
    return {}


def create_dependencies_data_structure(response_data, dependants_ids, dependencies_data, checked_packs):
    """ Recursively creates the packs' dependencies data structure for the installation requests
    (only required and uninstalled).

    Args:
        response_data (dict): The GET /search/dependencies response data.
        dependants_ids (list): A list of the dependant packs IDs.
        dependencies_data (list): The dependencies data structure to be created.
        checked_packs (list): Required dependants that were already found.
    """

    next_call_dependants_ids = []

    for dependency in response_data:
        # empty currentVersion field indicates the pack isn't installed yet
        if dependency.get('currentVersion'):
            continue

        dependants = dependency.get('dependants', {})
        for dependant in dependants.keys():
            is_required = dependants[dependant].get('level', '') == 'required'
            if dependant in dependants_ids and is_required and dependency.get('id') not in checked_packs:
                dependencies_data.append({
                    'id': dependency.get('id'),
                    'version': dependency.get('extras', {}).get('pack', {}).get('currentVersion')
                })
                next_call_dependants_ids.append(dependency.get('id'))
                checked_packs.append(dependency.get('id'))

    if next_call_dependants_ids:
        create_dependencies_data_structure(response_data, next_call_dependants_ids, dependencies_data, checked_packs)


def get_pack_dependencies(client, prints_manager, pack_data):
    """ Get the pack's required dependencies.

    Args:
        client (demisto_client): The configured client to use.
        prints_manager (ParallelPrintsManager): A prints manager object.
        pack_data (dict): Contains the pack ID and version.

    Returns:
        (list) The pack's dependencies.
    """
    pack_id = pack_data['id']

    try:
        response_data, status_code, _ = demisto_client.generic_request_func(
            client,
            path='/contentpacks/marketplace/search/dependencies',
            method='POST',
            body=[pack_data],
            accept='application/json'
        )

        if 200 <= status_code < 300:
            dependencies_data = []
            dependants_ids = [pack_id]
            reseponse_data = ast.literal_eval(response_data).get('dependencies', [])
            create_dependencies_data_structure(reseponse_data, dependants_ids, dependencies_data, dependants_ids)
            dependencies_str = ', '.join([dep['id'] for dep in dependencies_data])
            if dependencies_data:
                message = 'Found the following dependencies for pack {}:\n{}\n'.format(pack_id, dependencies_str)
                prints_manager.add_print_job(message, print_color, 0, LOG_COLORS.GREEN)
                prints_manager.execute_thread_prints(0)
            return dependencies_data
        else:
            result_object = ast.literal_eval(response_data)
            msg = result_object.get('message', '')
            err_msg = 'Failed to get pack {} dependencies - with status code {}\n{}\n'.format(pack_id, status_code, msg)
            raise Exception(err_msg)
    except Exception as e:
        err_msg = 'The request to get pack {} dependencies has failed. Reason:\n{}\n'.format(pack_id, str(e))
        raise Exception(err_msg)


def search_pack(client, prints_manager, pack_display_name):
    """ Make a pack search request.

    Args:
        client (demisto_client): The configured client to use.
        prints_manager (ParallelPrintsManager): Print manager object.
        pack_display_name (string): The pack display name.

    Returns:
        (dict): Returns the pack data if found, or empty dict otherwise.
    """

    try:
        # make the search request
        response_data, status_code, _ = demisto_client.generic_request_func(client,
                                                                            path='/contentpacks/marketplace/search',
                                                                            method='POST',
                                                                            body={"packsQuery": pack_display_name},
                                                                            accept='application/json')

        if 200 <= status_code < 300:
            result_object = ast.literal_eval(response_data)
            search_results = result_object.get('packs', [])
            pack_data = get_pack_data_from_results(search_results, pack_display_name)
            if pack_data:
                print_msg = 'Found pack {} in bucket!\n'.format(pack_display_name)
                prints_manager.add_print_job(print_msg, print_color, 0, LOG_COLORS.GREEN)
                prints_manager.execute_thread_prints(0)
                return pack_data

            else:
                print_msg = 'Did not find pack {} in bucket.\n'.format(pack_display_name)
                prints_manager.add_print_job(print_msg, print_color, 0, LOG_COLORS.YELLOW)
                prints_manager.execute_thread_prints(0)
                return {}
        else:
            result_object = ast.literal_eval(response_data)
            msg = result_object.get('message', '')
            err_msg = 'Pack {} search request failed - with status code {}\n{}'.format(pack_display_name,
                                                                                       status_code, msg)
            raise Exception(err_msg)
    except Exception as e:
        err_msg = 'The request to search pack {} has failed. Reason:\n{}'.format(pack_display_name, str(e))
        raise Exception(err_msg)


def install_packs(client, host, prints_manager, packs_to_install):
    """ Make a packs installation request.

    Args:
        client (demisto_client): The configured client to use.
        host (str): The server URL.
        prints_manager (ParallelPrintsManager): Print manager object.
        packs_to_install (list): A list of the packs to install.
    """

    request_data = {
        'packs': packs_to_install,
        'ignoreWarnings': True
    }

    # make the pack installation request
    try:
        response_data, status_code, _ = demisto_client.generic_request_func(client,
                                                                            path='/contentpacks/marketplace/install',
                                                                            method='POST',
                                                                            body=request_data,
                                                                            accept='application/json')

        if 200 <= status_code < 300:
            packs_str = '\n'.join([pack['id'] for pack in packs_to_install])
            message = 'Successully installed the following packs in server {}:\n{}\n'.format(host, packs_str)
            prints_manager.add_print_job(message, print_color, 0, LOG_COLORS.GREEN)
            prints_manager.execute_thread_prints(0)
        else:
            result_object = ast.literal_eval(response_data)
            message = result_object.get('message', '')
            err_msg = 'Failed to install packs - with status code {}\n{}\n'.format(status_code, message)
            raise Exception(err_msg)
    except Exception as e:
        err_msg = 'The request to install packs has failed. Reason:\n{}\n'.format(str(e))
        raise Exception(err_msg)


def search_pack_and_its_dependencies(client, prints_manager, pack_id, packs_to_install,
                                     installation_request_body, lock, is_nightly):
    """ Searches for the pack of the specified file path, as well as its dependencies,
        and updates the list of packs to be installed accordingly.

    Args:
        client (demisto_client): The configured client to use.
        prints_manager (ParallelPrintsManager): A prints manager object.
        pack_id (str): The id of the pack to be installed.
        packs_to_install (list): A list of packs to be installed.
        installation_request_body (list): A list of packs to be installed, in the request format.
        lock (Lock): A lock object.
        is_nightly (bool): Whether or not the build is a nightly build.
    """
    pack_data = []

    if not is_nightly:
        pack_display_name = get_pack_display_name(pack_id)
        if pack_display_name:
            pack_data = search_pack(client, prints_manager, pack_display_name)

    else:
        pack_data = get_pack_data(pack_id)

    if pack_data:
        dependencies = get_pack_dependencies(client, prints_manager, pack_data)

        current_packs_to_install = [pack_data]
        current_packs_to_install.extend(dependencies)

        lock.acquire()
        for pack in current_packs_to_install:
            if pack['id'] not in packs_to_install:
                packs_to_install.append(pack['id'])
                installation_request_body.append(pack)
        lock.release()


def get_pack_data(pack_id):
    metadata_path = os.path.join(PACKS_FULL_PATH, pack_id, PACK_METADATA_FILE)
    with open(metadata_path, 'r') as json_file:
        pack_metadata = json.load(json_file)
        version = pack_metadata.get('currentVersion')
        return {
            'id': pack_id,
            'version': version
        }


def add_pack_to_installation_request(pack_id, installation_request_body):
    metadata_path = os.path.join(PACKS_FULL_PATH, pack_id, PACK_METADATA_FILE)
    with open(metadata_path, 'r') as json_file:
        pack_metadata = json.load(json_file)
        version = pack_metadata.get('currentVersion')
        installation_request_body.append({
            'id': pack_id,
            'version': version
        })


def search_and_install_packs_and_their_dependencies(pack_ids, client, prints_manager, is_nightly=False):
    """ Searches for the packs from the specified list, searches their dependencies, and then installs them.
    Args:
        pack_ids (list): A list of the pack ids to search and install.
        client (demisto_client): The client to connect to.
        prints_manager (ParallelPrintsManager): A prints manager object.
        is_nightly (bool): Whether or not the build is a nightly build.

    Returns (list): A list of the installed packs' ids.
    """
    host = client.api_client.configuration.host
    msg = 'Starting to search and install packs in server: {}\n'.format(host)
    prints_manager.add_print_job(msg, print_color, 0, LOG_COLORS.GREEN)
    prints_manager.execute_thread_prints(0)

    packs_to_install = []  # we save all the packs we want to install, to avoid duplications
    installation_request_body = []  # the packs to install, in the request format

    if is_nightly:  # install all packs for nightly build
        for pack_id in os.listdir(PACKS_FULL_PATH):
            if pack_id not in IGNORED_FILES:
                pack_ids.append(pack_id)

        chunk_size = 50
        chunks = [pack_ids[x:x + chunk_size] for x in range(0, len(pack_ids), chunk_size)]

    else:
        for pack_id in ['Base', 'DeveloperTools']:
            packs_to_install.append(pack_id)
            add_pack_to_installation_request(pack_id, installation_request_body)

        chunks = [pack_ids]

    for chunk in chunks:
        lock = Lock()
        threads_list = []

        for pack_id in chunk:
            thread = Thread(target=search_pack_and_its_dependencies,
                            kwargs={'client': client,
                                    'prints_manager': prints_manager,
                                    'pack_id': pack_id,
                                    'packs_to_install': packs_to_install,
                                    'installation_request_body': installation_request_body,
                                    'lock': lock,
                                    'is_nightly': is_nightly})
            threads_list.append(thread)
        run_threads_list(threads_list)

        install_packs(client, host, prints_manager, installation_request_body)

    return packs_to_install

#
# apikey = 'D8E13A82D0DA0F14D7DE50535666DADB'
# host = 'https://ec2-34-222-130-94.us-west-2.compute.amazonaws.com'
# client = demisto_client.configure(base_url=host, api_key=apikey, verify_ssl=False)
# from Tests.test_content import ParallelPrintsManager
# prints_manager = ParallelPrintsManager(1)
# search_and_install_packs_and_their_dependencies([], client, prints_manager, is_nightly=True)
