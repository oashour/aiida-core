# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""`verdi code` command."""
from functools import partial

import click
import tabulate

from aiida.cmdline.commands.cmd_verdi import verdi
from aiida.cmdline.params import options, arguments
from aiida.cmdline.params.options.commands import code as options_code
from aiida.cmdline.utils import echo
from aiida.cmdline.utils.decorators import with_dbenv
from aiida.common.exceptions import InputValidationError


@verdi.group('code')
def verdi_code():
    """Setup and manage codes."""


def get_default(key, ctx):
    """
    Get the default argument using a user instance property
    :param value: The name of the property to use
    :param ctx: The click context (which will be used to get the user)
    :return: The default value, or None
    """
    try:
        value = getattr(ctx.code_builder, key)
        if value == '':
            value = None
    except KeyError:
        value = None

    return value


def get_computer_name(ctx):
    return getattr(ctx.code_builder, 'computer').label


def get_on_computer(ctx):
    return not getattr(ctx.code_builder, 'is_local')()


# pylint: disable=unused-argument
def set_code_builder(ctx, param, value):
    """Set the code spec for defaults of following options."""
    from aiida.orm.utils.builders.code import CodeBuilder
    ctx.code_builder = CodeBuilder.from_code(value)
    return value


@verdi_code.command('setup')
@options_code.LABEL()
@options_code.DESCRIPTION()
@options_code.INPUT_PLUGIN()
@options_code.ON_COMPUTER()
@options_code.COMPUTER()
@options_code.REMOTE_ABS_PATH()
@options_code.FOLDER()
@options_code.REL_PATH()
@options_code.PREPEND_TEXT()
@options_code.APPEND_TEXT()
@options.NON_INTERACTIVE()
@options.CONFIG_FILE()
@with_dbenv()
def setup_code(non_interactive, **kwargs):
    """Setup a new code."""
    from aiida.common.exceptions import ValidationError
    from aiida.orm.utils.builders.code import CodeBuilder

    if kwargs.pop('on_computer'):
        kwargs['code_type'] = CodeBuilder.CodeType.ON_COMPUTER
    else:
        kwargs['code_type'] = CodeBuilder.CodeType.STORE_AND_UPLOAD

    code_builder = CodeBuilder(**kwargs)

    try:
        code = code_builder.new()
    except InputValidationError as exception:
        echo.echo_critical('invalid inputs: {}'.format(exception))

    try:
        code.store()
        code.reveal()
    except ValidationError as exception:
        echo.echo_critical('Unable to store the Code: {}'.format(exception))

    echo.echo_success('Code<{}> {} created'.format(code.pk, code.full_label))


@verdi_code.command('duplicate')
@arguments.CODE(callback=set_code_builder)
@options_code.LABEL(contextual_default=partial(get_default, 'label'))
@options_code.DESCRIPTION(contextual_default=partial(get_default, 'description'))
@options_code.INPUT_PLUGIN(contextual_default=partial(get_default, 'input_plugin'))
@options_code.ON_COMPUTER(contextual_default=get_on_computer)
@options_code.COMPUTER(contextual_default=get_computer_name)
@options_code.REMOTE_ABS_PATH(contextual_default=partial(get_default, 'remote_abs_path'))
@options_code.FOLDER(contextual_default=partial(get_default, 'code_folder'))
@options_code.REL_PATH(contextual_default=partial(get_default, 'code_rel_path'))
@options_code.PREPEND_TEXT(contextual_default=partial(get_default, 'prepend_text'))
@options_code.APPEND_TEXT(contextual_default=partial(get_default, 'append_text'))
@options.NON_INTERACTIVE()
@click.option('--hide-original', is_flag=True, default=False, help='Hide the code being copied.')
@click.pass_context
@with_dbenv()
def code_duplicate(ctx, code, non_interactive, **kwargs):
    """Duplicate a code allowing to change some parameters."""
    from aiida.common.exceptions import ValidationError
    from aiida.orm.utils.builders.code import CodeBuilder

    if kwargs.pop('on_computer'):
        kwargs['code_type'] = CodeBuilder.CodeType.ON_COMPUTER
    else:
        kwargs['code_type'] = CodeBuilder.CodeType.STORE_AND_UPLOAD

    if kwargs.pop('hide_original'):
        code.hide()

    code_builder = ctx.code_builder
    for key, value in kwargs.items():
        if value is not None:
            setattr(code_builder, key, value)
    new_code = code_builder.new()

    try:
        new_code.store()
        new_code.reveal()
    except ValidationError as exception:
        echo.echo_critical('Unable to store the Code: {}'.format(exception))

    echo.echo_success('Code<{}> {} created'.format(new_code.pk, new_code.full_label))


@verdi_code.command()
@arguments.CODE()
@options.VERBOSE()
@with_dbenv()
def show(code, verbose):
    """Display detailed information for a code."""
    from aiida.orm.utils.repository import FileType

    table = []
    table.append(['PK', code.pk])
    table.append(['UUID', code.uuid])
    table.append(['Label', code.label])
    table.append(['Description', code.description])
    table.append(['Default plugin', code.get_input_plugin_name()])

    if code.is_local():
        table.append(['Type', 'local'])
        table.append(['Exec name', code.get_execname()])
        table.append(['List of files/folders:', ''])
        for obj in code.list_objects():
            if obj.type == FileType.DIRECTORY:
                table.append(['directory', obj.name])
            else:
                table.append(['file', obj.name])
    else:
        table.append(['Type', 'remote'])
        table.append(['Remote machine', code.get_remote_computer().label])
        table.append(['Remote absolute path', code.get_remote_exec_path()])

    table.append(['Prepend text', code.get_prepend_text()])
    table.append(['Append text', code.get_append_text()])

    if verbose:
        table.append(['Calculations', len(code.get_outgoing().all())])

    click.echo(tabulate.tabulate(table))


@verdi_code.command()
@arguments.CODES()
@options.VERBOSE()
@options.DRY_RUN()
@options.FORCE()
@with_dbenv()
def delete(codes, verbose, dry_run, force):
    """Delete a code.

    Note that codes are part of the data provenance, and deleting a code will delete all calculations using it.
    """
    from aiida.manage.database.delete.nodes import delete_nodes

    verbosity = 1
    if force:
        verbosity = 0
    elif verbose:
        verbosity = 2

    node_pks_to_delete = [code.pk for code in codes]
    delete_nodes(node_pks_to_delete, dry_run=dry_run, verbosity=verbosity, force=force)


@verdi_code.command()
@arguments.CODES()
@with_dbenv()
def hide(codes):
    """Hide one or more codes from `verdi code list`."""
    for code in codes:
        code.hide()
        echo.echo_success('Code<{}> {} hidden'.format(code.pk, code.full_label))


@verdi_code.command()
@arguments.CODES()
@with_dbenv()
def reveal(codes):
    """Reveal one or more hidden codes in `verdi code list`."""
    for code in codes:
        code.reveal()
        echo.echo_success('Code<{}> {} revealed'.format(code.pk, code.full_label))


@verdi_code.command()
@arguments.CODE()
@arguments.LABEL()
@with_dbenv()
def relabel(code, label):
    """Relabel a code."""
    old_label = code.full_label

    try:
        code.relabel(label)
    except InputValidationError as exception:
        echo.echo_critical('invalid code label: {}'.format(exception))
    else:
        echo.echo_success('Code<{}> relabeled from {} to {}'.format(code.pk, old_label, code.full_label))


@verdi_code.command('list')
@options.COMPUTER(help='Filter codes by computer.')
@options.INPUT_PLUGIN(help='Filter codes by calculation input plugin.')
@options.ALL(help='Include hidden codes.')
@options.ALL_USERS(help='Include codes from all users.')
@click.option('-o', '--show-owner', 'show_owner', is_flag=True, default=False, help='Show owners of codes.')
@with_dbenv()
def code_list(computer, input_plugin, all_entries, all_users, show_owner):
    """List the available codes."""
    from aiida.orm import Code  # pylint: disable=redefined-outer-name
    from aiida import orm

    qb_user_filters = dict()
    if not all_users:
        user = orm.User.objects.get_default()
        qb_user_filters['email'] = user.email

    qb_computer_filters = dict()
    if computer is not None:
        qb_computer_filters['name'] = computer.label

    qb_code_filters = dict()
    if input_plugin is not None:
        qb_code_filters['attributes.input_plugin'] = input_plugin.name

    # If not all_entries, hide codes with HIDDEN_KEY extra set to True
    if not all_entries:
        qb_code_filters['or'] = [{
            'extras': {
                '!has_key': Code.HIDDEN_KEY
            }
        }, {
            'extras.{}'.format(Code.HIDDEN_KEY): {
                '==': False
            }
        }]

    echo.echo('# List of configured codes:')
    echo.echo("# (use 'verdi code show CODEID' to see the details)")

    showed_results = False

    # pylint: disable=invalid-name
    if computer is not None:
        qb = orm.QueryBuilder()
        qb.append(Code, tag='code', filters=qb_code_filters, project=['id', 'label'])
        # We have a user assigned to the code so we can ask for the
        # presence of a user even if there is no user filter
        qb.append(orm.User, with_node='code', project=['email'], filters=qb_user_filters)
        # We also add the filter on computer. This will automatically
        # return codes that have a computer (and of course satisfy the
        # other filters). The codes that have a computer attached are the
        # remote codes.
        qb.append(orm.Computer, with_node='code', project=['name'], filters=qb_computer_filters)
        qb.order_by({Code: {'id': 'asc'}})
        showed_results = qb.count() > 0
        print_list_res(qb, show_owner)

    # If there is no filter on computers
    else:
        # Print all codes that have a computer assigned to them
        # (these are the remote codes)
        qb = orm.QueryBuilder()
        qb.append(Code, tag='code', filters=qb_code_filters, project=['id', 'label'])
        # We have a user assigned to the code so we can ask for the
        # presence of a user even if there is no user filter
        qb.append(orm.User, with_node='code', project=['email'], filters=qb_user_filters)
        qb.append(orm.Computer, with_node='code', project=['name'])
        qb.order_by({Code: {'id': 'asc'}})
        print_list_res(qb, show_owner)
        showed_results = showed_results or qb.count() > 0

        # Now print all the local codes. To get the local codes we ask
        # the dbcomputer_id variable to be None.
        qb = orm.QueryBuilder()
        comp_non_existence = {'dbcomputer_id': {'==': None}}
        if not qb_code_filters:
            qb_code_filters = comp_non_existence
        else:
            new_qb_code_filters = {'and': [qb_code_filters, comp_non_existence]}
            qb_code_filters = new_qb_code_filters
        qb.append(Code, tag='code', filters=qb_code_filters, project=['id', 'label'])
        # We have a user assigned to the code so we can ask for the
        # presence of a user even if there is no user filter
        qb.append(orm.User, with_node='code', project=['email'], filters=qb_user_filters)
        qb.order_by({Code: {'id': 'asc'}})
        showed_results = showed_results or qb.count() > 0
        print_list_res(qb, show_owner)
    if not showed_results:
        echo.echo('# No codes found matching the specified criteria.')


def print_list_res(qb_query, show_owner):
    """Print a list of available codes."""
    # pylint: disable=invalid-name
    for tuple_ in qb_query.all():
        if len(tuple_) == 3:
            (pk, label, useremail) = tuple_
            computername = None
        elif len(tuple_) == 4:
            (pk, label, useremail, computername) = tuple_
        else:
            echo.echo_warning('Wrong tuple size')
            return

        if show_owner:
            owner_string = ' ({})'.format(useremail)
        else:
            owner_string = ''
        if computername is None:
            computernamestring = ''
        else:
            computernamestring = '@{}'.format(computername)
        echo.echo('* pk {} - {}{}{}'.format(pk, label, computernamestring, owner_string))
