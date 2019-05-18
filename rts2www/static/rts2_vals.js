function get_rts2()
{



$.ajax
({
  type: "GET",
  url: "device",
  dataType: 'json',
  withCredentials : true,
  data: '{ "comment" }',
})
	.done(function(data)
	{	
		try
		{		
			$("button#dropdownMenuStatus").html(data['rts2_status']);
		}
		catch(err)
		{
			$("h4#rts2_status").text(err);

		}
		try
		{
			display_focus(data);
		}
		catch(err)
		{
			console.log("Problem with display_focus ", err);
		}
		try
		{
			check_drivers(data);
		}
		catch(err)
		{
			console.log("Problem with check_drivers", err)
		}
		try
		{
			do_filters(data);
		}
		catch(err)
		{
			console.log("Problem with do_filters", err)
		}
		try
		{
			do_queues(data);
		}
		catch(err)
		{
			console.log("Problem with do_queues", err);
		}

		$( "span.rts2_val" ).each(function(index)
		{
			var dev = $( this ).attr( "device" ); 
			var valname = $( this ).attr( "valname" );
			var type = $( this ).attr( "rts2type" );
			var good_data = false;
			if(dev in data)
			{
				try
				{
					if(valname in data[dev]["d"])
						var good_data = true;
				}
				catch(err)
				{
					console.log(err)
				}
			}

			if( good_data)
			{
				$("div#errmsg").text("");
				if(type == "bool")
				{
					$(this).text(data[dev]["d"][valname][1] ? "True" : "False" );
				}
				else if( type == "time" )
				{
					var now = new Date();
					var d = new Date(data[dev]["d"][valname][1]*1000)
					var h = ("0"+d.getHours()).slice(-2);
					var m = ("0"+d.getMinutes()).slice(-2);
					var s = ("0"+d.getSeconds()).slice(-2);
					var delta = d-now;
										

					$(this).text(h+":"+m+":"+s+" ("+parseInt(delta/60000.0)+"m)");

					
				}
				else if(type == "float")
				{
					var num = data[dev]["d"][valname][1]
					$(this).text(num.toFixed(4))
				}
				else
				{
					$(this).text(data[dev]["d"][valname][1] );
				}
			}
			else
			{
				//console.log("There was a problem getting rts2 data");
				//console.log(data);
				//$("div#errmsg").text("Could not get device "+dev+", is RTS2 on?")
			}


		});
	})
	.fail(function(jqXHR, textStatus, errorThrown){
		console.log(jqXHR);
		console.log(textStatus);
		console.log(errorThrown);
	})
.always( function() {setTimeout(get_rts2, 5000 )} )
}

function reload_image()
{
	d=new Date()
	$("img#latest_image").attr("src", "image/last.jpg?"+d.getDate())
	setTimeout( reload_image, 5000 )
}

function do_filters(data)
{
	var filters = data["W0"]["d"]["filter_names"][1].split(" ");
	var current_filter = data["W0"]["d"]["loadedFilter"][1];
	
	for(filter in filters)
	{
		if(filters[filter] == "")
			continue

		if( $("div#"+filters[filter]).length == 0 )
		{
			$("<div class='filter' id="+filters[filter]+">"+filters[filter]+"</div>").appendTo("div#filter_div")
			.css("cursor", "pointer")
			.on("dblclick", function(evt) 
			{
				console.log(evt)
				console.log("Moving to filter "+ evt.target.id )
				$("i#filterwait").css("display", "inline-flex")
				$.ajax({
					type: "GET",
					url: "filters/"+evt.target.id
				}).fail(function(jqXHR, textStatus, errorThrown){
					console.log("Filter move failed");
					console.log(jqXHR);
					console.log(textStatus);
					console.log(errorThrown);
				}).done(function()
				{
					console.log("filterwheel success")
					$("i#filterwait").css("display", "none")
				})
				
			})
		}
		else
			$("div#"+filters[filter]).css("background-color", "none")

		if(filters[filter] == current_filter)
			$("div#"+current_filter).css("background-color", "lightgreen")
		else
		{
			$("div#"+filters[filter]).css("background-color", "transparent")
		}

	}
}


function do_queues(data)
{

	var queues = data["SEL"]["d"]["plan_names"][1];
	$("span#inner_plan_queue").empty();

	for(queue in queues)
	{
		var clean_queue = queues[queue].replace(/\(/g, "_");
		clean_queue = clean_queue.replace(/\)/g, "_");
		if(queues[queue] == "")
			continue

		if( $( "div#"+clean_queue).length == 0 )
			$("span#inner_plan_queue").append( "<div class=plan_queue id="+clean_queue+">"+queues[queue]+"</div>" )


	}




}

function do_focusrun()
{
	$.ajax
	({
	  type: "GET",
	  url: "focus/focusrun",
	  dataType: 'json',
	  withCredentials : true,
	}).done(function(evt) {console.log("focusrun success")})

}

function do_exposure(exptime)
{
	$.ajax
	({
	  type: "GET",
	  url: "exposure/"+parseFloat(exptime),
	  dataType: 'json',
	  withCredentials : true,
	}).done(function(evt) {console.log("exp success")})

}

function get_messages(num)
{
	$.getJSON("db/message_json/"+num,function(data)
	{
		//$("textarea#rts2_messages").text("")
		temp=""
		var divsel = $("div#rts2_messages")
		msgtypes = {1:"rts2error", 4:"rts2info", 2:"rts2warn"};
		var lastmsg = $("p.rts2_message").last().text().slice(0,26);
		if(lastmsg != "")
		{
			lastmsg_time = new Date(lastmsg)
		}
		else
		{	
			lastmsg_time = new Date("2000-01-01 00:00:00")
		}
		for(ii in data)
		{
			//var current_messages= $("p#rts2_messages").val()
			//divsel.append($("p").text(data[ii].time+": "+data[ii].message+"\n").addClass(data[ii].type))
			msgtime = new Date(data[ii].time)
			if(msgtime > lastmsg_time)
			{//Only add new messages
				
				$("<p class='rts2_message'>"+"</p>")
				.addClass(msgtypes[data[ii].type])
				.text(data[ii].time+": "+data[ii].message)
				.appendTo("div#rts2_messages")
			}
			//temp = temp+data[ii].time+": "+data[ii].message+"\n"
		}
		//console.log("messages")
		//divsel.scrollTop(divsel[0].scrollHeight)
		//$("textarea#rts2_messages").val(temp);
	})
	setTimeout( function(){get_messages(10)}, 10000)
}

function main()
{
	$("input#FOC_DEF").keypress(
		function(event)
		{
			if(event.which == 13)
			{
				event.preventDefault();
				var focus = parseInt($(this).val())
				$.ajax({
					type:"GET",
					url:"/device/set/F0/FOC_DEF/"+focus
				})
				$(this).blur();
			}
		}
	)

	//reload_image();
	get_rts2();
	show_exp_num();
	get_messages(50);

}

function show_exp_num()
{
	$.ajax({
		type:"Get",
		url:"rts2scripts",
		dataType:"json",
		withCredentials: true,
	}).done(
		function(data)
		{
			$("span#exp_num").text("Exposure Number "+data.script_exp_num+" of "+data.total_num_exps)
		}
	)
	setTimeout(show_exp_num, 10000 );
}


function check_drivers(data)
{
	$("p.rts2_device_check").each(
		function()
		{
			if(data.hasOwnProperty($(this).attr("id")))
			{
				$(this).css("background", "white")
			}
			else
			{
				
				$(this).css("background", "red")
			}
		}
	)
}

function display_focus(data)
{	

	if(!$("input#FOC_DEF").is(":focus"))
		$("input#FOC_DEF").val(data.F0.d.FOC_DEF[1] );
}



function startup()
{
	$.ajax
	({
		type: "GET",
		  url: "queuestart",

	})
}

function change_rts2_state(state)
{
	$.ajax
	({
		type: "GET",
		url: "rts2state/"+state,
	})
}


