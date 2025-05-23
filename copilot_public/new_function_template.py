import json
import types
import unitymol_zmq

def execute_unitymol_command(self, command: str):

    try:
        # Execute the command
        result = unitymol_zmq.unitymol.send_command_clean(command)

        return f"Command '{command}' returned {result}"

    except Exception as e:
        print(f"Error executing command '{command}': {e}")
        return f"Command '{command}' failed with error {e} and feedback {result}"        


def load_protein_into_unitymol(self, protein_pdb_id: str):

    try:
        # Execute the command
        result = unitymol_zmq.unitymol.send_command_clean(f"fetch('{protein_pdb_id}')")

        return f"Opening PDB ID '{protein_pdb_id}' returned {result}"

    except Exception as e:
        print(f"Error fetching PDB ID '{protein_pdb_id}': {e}")
        return f"Fetch('{protein_pdb_id}') failed with error {e} and feedback {result}"        


def translate_to_protein(self, seq: str, pname=None):
    from Bio.Seq import Seq

    nucleotide_seq = Seq(seq)
    protein_seq = nucleotide_seq.translate()
    if pname:
        return f"The protein sequence of {seq} is `>{pname}\n{protein_seq}`"
    else:
        return f"The protein sequence of {seq} is `>protein\n{protein_seq}`"


def get_smiles_feature(self, smiles):
    from rdkit import Chem
    from rdkit.Chem.QED import properties
    
    try:
        mol = Chem.MolFromSmiles(smiles)
    except:
        return "Error: Not a valid SMILES string"
    p = properties(mol)
    formatted_result = (
        f"Molecular Weight: {p.MW:.2f}, "
        f"LOGP: {p.ALOGP:.2f}, "
        f"HBA (Hydrogen Bond Acceptors): {p.HBA}, "
        f"HBD (Hydrogen Bond Donors): {p.HBD}, "
        f"PSA (Polar Surface Area): {p.PSA:.2f}, "
        f"ROTB (Rotatble Bonds): {p.ROTB}, "
        f"AROM (Aromatic Rings): {p.AROM}"
    )
    return formatted_result


def calculate_mol_properties(self, smiles_key):
    from rdkit import Chem
    from rdkit.Chem.QED import properties
    from chatmol_fn import redis_reader, redis_writer

    smiles_list = redis_reader(smiles_key)
    
    results = []
    for smiles in smiles_list:
        try:
            mol = Chem.MolFromSmiles(smiles)
        except:
            return "Error: Not a valid SMILES string"
        p = properties(mol)
        result_dict = {
            "Molecule": smiles, 
            "Molecular Weight": float(f"{p.MW:.2f}"), 
            "LOGP": float(f"{p.ALOGP:.2f}"), 
            "HBA (Hydrogen Bond Acceptors)": p.HBA, 
            "HBD (Hydrogen Bond Donors)": p.HBD, 
            "PSA (Polar Surface Area)": float(f"{p.PSA:.2f}"), 
            "ROTB (Rotatable Bonds)": p.ROTB, 
            "AROM (Aromatic Rings)": p.AROM
        }
        results.append(result_dict)
    # Save the results into redis cache
    redis_key = "mol_property_table"
    redis_writer(redis_key,results)
    # Convert to string!
    return f"molecule property table has been saved to redis cache with a redis key: {redis_key} \\n" + str(results)

def capped(self, smiles):
    """ cap one amino acid """
    from rdkit import Chem
    def update_idx(removed, current):
        if current>removed:
            current -= 1
        return current
    
    try:
        mol = Chem.MolFromSmiles(smiles)
    except:
        return "Error: Not a valid SMILES string"
    
    acetyl_smiles = "CC(=O)N"
    methyl_amide_smiles = "NC"
    m_idx =  0
    ace_mol = Chem.MolFromSmiles(acetyl_smiles)
    methyl_mol = Chem.MolFromSmiles(methyl_amide_smiles)
    
    combined_mol = Chem.CombineMols(mol,ace_mol)
    combined_mol = Chem.CombineMols(combined_mol, methyl_mol)

    backbone_matches = "NC[C:1](=[O:2])-[OD1]"
    backbone = Chem.MolFromSmarts(backbone_matches)
    
    cp_nh2 = Chem.MolFromSmarts(methyl_amide_smiles)
    cp_cooh = Chem.MolFromSmarts('[C:1](=[O:2])-N')
    OH = combined_mol.GetSubstructMatches(backbone)[0][-1]
    C1 = combined_mol.GetSubstructMatches(backbone)[0][-3]
    NH2 = combined_mol.GetSubstructMatches(backbone)[0][0]
    METH = combined_mol.GetSubstructMatches(cp_nh2)[-1][m_idx]
    ACE = combined_mol.GetSubstructMatches(cp_cooh)[-1][-1]
    
    capped_mol = Chem.EditableMol(combined_mol)
    capped_mol.RemoveAtom(OH)
    C1 = update_idx(OH,C1)
    NH2 = update_idx(OH,NH2)
    METH = update_idx(OH,METH)
    ACE = update_idx(OH,ACE)
    capped_mol.AddBond(C1, METH, order=Chem.rdchem.BondType.SINGLE)

    bonds = capped_mol.GetMol().GetBonds()
    connected = []
    for bond in bonds:
        if bond.GetBeginAtom().GetIdx() == NH2:
            connected.append(bond.GetEndAtom().GetIdx()-1 \
                            if bond.GetEndAtom().GetIdx()>NH2 \
                            else bond.GetEndAtom().GetIdx())
        elif bond.GetEndAtom().GetIdx() == NH2:
            connected.append(bond.GetBeginAtom().GetIdx()-1 \
                            if bond.GetBeginAtom().GetIdx()>NH2 \
                            else bond.GetBeginAtom().GetIdx())
            
    capped_mol.RemoveAtom(NH2)
    ACE = update_idx(NH2,ACE)
    for conn in connected:
        capped_mol.AddBond(conn, ACE, order=Chem.rdchem.BondType.SINGLE)
    capped_smi = Chem.MolToSmiles(capped_mol.GetMol())
    return f"After capping (adding ace and nme), the smiles is `{capped_smi}`"


def smiles_similarity(self, smiles1, smiles2, types="ECFP"):
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem import MACCSkeys
    from rdkit.DataStructs import TanimotoSimilarity
    
    def get_fingerprint(smiles, types):
        try:
            molecule = Chem.MolFromSmiles(smiles)
        except:
            return "Error: Not a valid SMILES string"
        # ECFP
        fp = AllChem.GetMorganFingerprint(molecule, 2)
        if types == "FCFP":
            fp = AllChem.GetMorganFingerprint(
                                    molecule, 2,
                                    useFeatures=True,
                                    useChirality=True
                                    )            
        elif types == "RDK":
            fp = AllChem.RDKFingerprint(molecule)
        elif types == "MACC":
            fp = MACCSkeys.GenMACCSKeys(molecule)
        return fp

    fp1, fp2 = get_fingerprint(smiles1,types), get_fingerprint(smiles2,types)
    similarity = TanimotoSimilarity(fp1, fp2)
    
    return f"Using {types} fingerprint and Tanimoto, the result is {similarity:.2f}"


function_descriptions = [{ # This is the description of the function
    "type": "function",
    "function": {
        "name": "execute_unitymol_command",
        "description": "Execute a UnityMol API command and return the result.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The UnityMol API command to execute"},
            },
        },
        "required": ["command"],
    },
},
{
    "type": "function",
    "function": {
        "name": "load_protein_into_unitymol",
        "description": "fetch a protein from PDB",
        "parameters": {
            "type": "object",
            "properties": {
                "protein_pdb_id": {"type": "string", "description": "PDB ID of a protein. It is usually a four character code"},
            },
        },
        "required": ["protein_pdb_id"],
    },
},                         
{  # This is the description of the function
    "type": "function",
    "function": {
        "name": "translate_to_protein",
        "description": "Translate a DNA/RNA sequence to a protein sequence",
        "parameters": {
            "type": "object",
            "properties": {
                "seq": {"type": "string", "description": "The DNA/RNA sequence"},
            },
        },
        "required": ["seq"],
    },
},
{
    "type": "function",
    "function": {
        "name": "get_smiles_feature",
        "description": "Input a smiles, and will return molecule weight, logp, \
                        HBA(Hydrogen Bond Acceptors), HBD(Hydrogen Bond Donors) \
                        and PSA(Polar Surface Area) values",
        "parameters": {
            "type": "object",
            "properties": {
                "smiles": {"type": "string", "description": "The smiles sequence"},
            },
        },
        "required": ["smiles"],
    }
},
{
    "type": "function",
    "function": {
        "name": "calculate_mol_properties",
        "description": "Calculate properties for a list of smiles started in Redis cache, and will return a list of molecular \
                        properties, including weight, logp, HBA(Hydrogen Bond Acceptors), HBD(Hydrogen Bond Donors) \
                        PSA(Polar Surface Area) values, ROTB(Rotatable Bonds) and AROM(Aromatic Rings)",
        "parameters": {
            "type": "object",
            "properties": {
                "smiles_key": {"type": "string", "description": "Redis key for a list of smiles"},
            },
        },
        "required": ["smiles_key"],
    }
},
{
    "type": "function",
    "function": {
        "name": "capped",
        "description": "Input a smiles, and will return a capped smiles, which \
                        means adding ACE and NME to the smiles to prevent or \
                        block unwanted reactions.",
        "parameters": {
            "type": "object",
            "properties": {
                "smiles": {"type": "string", "description": "The smiles sequence"},
            },
        },
        "required": ["smiles"],
    }
},
{
    "type": "function",
    "function": {
        "name": "smiles_similarity",
        "description": "Input two smiles and a fingerprint method (if not provided, \
                        ECFP - the default morgan fingerprint will be used) and \
                        return the TanimotoSimilarity",
        "parameters": {
            "type": "object",
            "properties": {
                "smiles1": {"type": "string", "description": "The smiles sequence"},
                "smiles2": {"type": "string", "description": "The smiles sequence"},
                "types": {"type": "string", "description": "The fingerprint method"},
            },
        },
        "required": ["smiles1", "smiles2"],
    }
}]

test_data = {
    "execute_unitymol_command": {
        "input": {
            "self": None,
            "command": "getSelectionListString()",
        },
        "output": "The list of current selections as bracketed list",
    },
    "load_protein_into_unitymol": {
        "input": {
            "self": None,
            "protein_pdb_id": "1kx2",
        },
        "output": "Characteristics of this protein database file",
    },
    "translate_to_protein": {
        "input": {
            "self": None,
            "seq": "ATGCGAATTTGGGCCC",
        },
        "output": "The protein sequence of ATGCGAATTTGGGCCC is `>protein\nMRFL`",
    },
    "get_smiles_feature": {
        "input": {
            "self": None,
            "smiles": "C[C@H](N)C(=O)N[C@@H](CS)C(=O)N[C@@H](CS)C(=O)O",
        },
        "output": "Molecular Weight: 295.39, LOGP: -1.75, HBA (Hydrogen Bond Acceptors): \
                   5, HBD (Hydrogen Bond Donors): 6, PSA (Polar Surface Area): 121.52",
    },
    "calculate_mol_properties": {
        "input": {
            "self": None,
            "smiles_key": "DenovoGen_smiles",
        },
        "output": "Molecular Weight: 295.39, LOGP: -1.75, HBA (Hydrogen Bond Acceptors): \
                   5, HBD (Hydrogen Bond Donors): 6, PSA (Polar Surface Area): 121.52",
    },
    "capped": {
        "input": {
            "self": None,
            "smiles": "N[C@@H](CS)C(=O)O",
        },
        "output": "After capping (adding ace and nme), the smiles is \
                   `CNC(=O)[C@H](CS)NC(C)=O`",
    },
    "smiles_similarity": {
        "input": {
            "self": None,
            "smiles1": "N[C@@H](CS)C(=O)O",
            "smiles2": "N[C@@H](CS)C(=O)O",
        },
        "output": "Using ECFP fingerprint and Tanimoto, the result is 1.00",
    }
}


def predict_rna_secondary_structure(self, rna_seq: str):
    from seqfold import fold, dg, dot_bracket
    """
    Predict the secondary structure of an RNA sequence using the seqfold library.

    Parameters:
    - rna_seq (str): The RNA sequence to be analyzed.

    Returns:
    - A dictionary with the minimum free energy and the dot-bracket representation of the structure.
    """
    mfe = dg(rna_seq)
    structs = fold(rna_seq)
    dot_bracket_structure = dot_bracket(rna_seq, structs)

    return f"Minimum Free Energy (MFE): `{mfe}`\nDot-Bracket Structure: `{dot_bracket_structure}`"

# Update the function description in the function_descriptions list
function_descriptions.append({
    "type": "function",
    "function": {
        "name": "predict_rna_secondary_structure",
        "description": "Predict the secondary structure of an RNA sequence using the seqfold library",
        "parameters": {
            "type": "object",
            "properties": {
                "rna_seq": {"type": "string", "description": "The RNA sequence"},
            },
        },
        "required": ["rna_seq"],
    },
})

# Update test data for the new function
test_data["predict_rna_secondary_structure"] = {
    "input": {
        "self": None,
        "rna_seq": "GGGAGGTCGTTACATCTGGGTAACACCGGTACTGATCCGGTGACCTCCC",
    },
    "output": {"Minimum Free Energy (MFE): `-13.4`\nDot-Bracket Structure: `((((((((.((((......))))..((((.......)))).))))))))`"
    },
}



def predict_logp_from_smiles(self, smiles: str):
    from rdkit import Chem
    from rdkit.Chem import Crippen
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "Invalid SMILES string"
    logp = Crippen.MolLogP(mol)
    return f"The predicted logP value for the molecule {smiles} is {logp}"

function_descriptions.append({
    "type": "function",
    "function": {
        "name": "predict_logp_from_smiles",
        "description": "Predicts the logP value of a molecule from its SMILES notation",
        "parameters": {
            "type": "object",
            "properties": {
                "smiles": {"type": "string", "description": "The SMILES notation of the molecule"},
            },
        },
        "required": ["smiles"],
    },
})

test_data["predict_logp_from_smiles"] = {
    "input": {
        "self": None,
        "smiles": "CCO",
    },
    "output": "The predicted logP value for the molecule CCO is 0.4605",  # Example output
}

### DO NOT MODIFY BELOW THIS LINE ###
def get_all_functions():
    all_functions = []
    global_functions = globals()
    for _, func in global_functions.items():
        if isinstance(func, types.FunctionType):
            all_functions.append(func)
    return all_functions

def get_info():
    return {"functions": get_all_functions(), "descriptions": function_descriptions}

def test_new_function(function, function_name, test_data):
    return (
        function(**test_data[function_name]["input"])
        == test_data[function_name]["output"]
    )
